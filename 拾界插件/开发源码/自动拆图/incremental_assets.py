"""Partial quality findings do not discard usable work. Resume data stays in RAM."""
import base64,copy,hashlib,json,re
from pathlib import Path

def pending_generation(node):
 """Visual review findings do not make already produced pixels missing."""
 if node.get('type')!='image' or node.get('versionArchived'):return False
 record=node.get('generationRecord')
 return node.get('pendingGeneration') is True or node.get('provenance') in ('pending-image-generation','source-crop-fallback') or (isinstance(record,dict) and record.get('actualImageGeneration') is False) or not node.get('src')

def _resume_key(node):
 if node.get('assetKind')=='background':return ('background',)
 if node.get('sourceTextId'):return ('text',node['sourceTextId'])
 if node.get('sourceVectorId'):return ('vector',node['sourceVectorId'])
 ident=node.get('sourceEntityId') or node.get('sourceAssetId')
 if ident:
  ink=(node.get('sourceInkColor') or node.get('fill')) if node.get('type')=='path' else None
  return ('asset',ident,ink)
 return ('id',node['id'])

def _insert_missing(existing,planned):
 """Insert missing IDs near their plan anchors without sorting existing IDs."""
 result=list(existing)
 for index,ident in enumerate(planned):
  if ident in result:continue
  before=next((other for other in reversed(planned[:index]) if other in result),None)
  after=next((other for other in planned[index+1:] if other in result),None)
  position=result.index(before)+1 if before is not None else result.index(after) if after is not None else len(result)
  result.insert(position,ident)
 return result

def recover_pending_scene(previous):
 """New snapshots carry the original pending IDs; no native rebuild is needed."""
 recognition=previous.get('recognition',{})
 if not isinstance(recognition.get('resumePendingNodes'),list):return None
 scene=copy.deepcopy(previous);known={n['id'] for n in scene['nodes']}
 scene['nodes'].extend(copy.deepcopy(n) for n in recognition['resumePendingNodes'] if n['id'] not in known)
 by_id={n['id']:n for n in scene['nodes']}
 order=_insert_missing([ident for ident in recognition.get('resumeNodeOrder',[]) if ident in by_id],list(by_id))
 scene['nodes']=[by_id[ident] for ident in order]
 scene['groups']=copy.deepcopy(recognition.get('resumeGroups',scene.get('groups',[])))
 return scene

def merge_resume_scene(planned,previous):
 """Retain completed objects verbatim, recovering only absent plan members."""
 scene=copy.deepcopy(previous);old_nodes=scene['nodes'];old_ids={n['id'] for n in old_nodes}
 by_key={}
 for node in old_nodes:
  if node.get('versionArchived'):continue
  key=_resume_key(node)
  if key in by_key:raise ValueError('续拆图层来源重复，无法安全匹配；保留原工程')
  by_key[key]=node
 mapping={};additions=[];used_names={n.get('name') for n in [*old_nodes,*scene.get('groups',[])]}
 for node in planned['nodes']:
  if node.get('versionArchived') and node['id'] in old_ids:
   mapping[node['id']]=node['id'];continue
  old=by_key.get(_resume_key(node))
  if old is not None:mapping[node['id']]=old['id']
  else:
   # Native objects already existed when the first snapshot was published.
   # Their later absence is an edit, not unfinished image generation.
   if node.get('type')!='image':continue
   if node['id'] in old_ids:raise ValueError('续拆新图层标识与已有图层冲突')
   candidate=copy.deepcopy(node);base=candidate.get('name') or '图层';name=base;index=2
   while name in used_names:name=base+'_'+str(index);index+=1
   candidate['name']=name;used_names.add(name)
   mapping[node['id']]=node['id'];additions.append(candidate)
 planned_ids=[mapping[n['id']] for n in planned['nodes'] if n['id'] in mapping]
 new_ids={n['id'] for n in additions};all_nodes={n['id']:n for n in [*old_nodes,*additions]}
 old_groups=scene.get('groups',[]);groups={g['id']:g for g in old_groups};group_order=[g['id'] for g in old_groups]
 planned_groups=[{**copy.deepcopy(g),'children':[mapping.get(ident,ident) for ident in g['children']]} for g in planned.get('groups',[])]
 planned_group_ids={g['id'] for g in planned_groups};owners={ident:g['id'] for g in old_groups for ident in g['children']}
 # Only absent members may enter a recovered group; existing ownership is final.
 for group in reversed(planned_groups):
  extra=[ident for ident in group['children'] if ident not in owners and (ident in new_ids or (ident in planned_group_ids and ident in groups and ident not in group_order))]
  if group['id'] in groups:
   target=groups[group['id']];target['children']=_insert_missing(target['children'],[ident for ident in group['children'] if ident in target['children'] or ident in extra])
  elif extra:
   groups[group['id']]={**group,'children':extra}
  for ident in extra:owners[ident]=group['id']
 for group in planned_groups:
  if group['id'] in groups and group['id'] not in group_order:group_order.append(group['id'])
 def root(ident):
  seen=set()
  while ident in owners:
   if ident in seen:raise ValueError('续拆分组存在循环')
   seen.add(ident);ident=owners[ident]
  return ident
 roots=list(dict.fromkeys(root(n['id']) for n in old_nodes));wanted=list(dict.fromkeys(root(ident) for ident in planned_ids))
 roots=_insert_missing(roots,wanted)
 def leaves(ident,seen=None):
  if ident in all_nodes:return [ident]
  if ident not in groups:raise ValueError('续拆分组引用了未知成员')
  seen=set() if seen is None else seen
  if ident in seen:raise ValueError('续拆分组存在循环')
  return [leaf for child in groups[ident]['children'] for leaf in leaves(child,seen|{ident})]
 ordered=[ident for ident in roots for ident in leaves(ident)]
 if len(ordered)!=len(set(ordered)) or set(ordered)!=set(all_nodes):raise ValueError('续拆图层归属不完整')
 if [ident for ident in ordered if ident in old_ids]!=[n['id'] for n in old_nodes]:raise ValueError('现有分组顺序不连续，续拆不能改变已完成图层的顺序')
 scene['nodes']=[all_nodes[ident] for ident in ordered];scene['groups']=[groups[ident] for ident in group_order]
 for key in ('delivery','_sessionId'):scene.pop(key,None)
 return scene

def effective_locked_ids(scene):
 """Node and ancestor locks share one interpretation across model operations."""
 entries={n['id']:n for n in [*scene.get('nodes',[]),*scene.get('groups',[])]}
 locked=set();pending=[ident for ident,n in entries.items() if n.get('locked')]
 while pending:
  ident=pending.pop()
  if ident in locked:continue
  locked.add(ident);pending.extend(entries.get(ident,{}).get('children',[]))
 return locked

def review_or_pending(review):
 try:return review()
 except InterruptedError:raise
 except Exception as error:
  note='最终画面复核未完成：'+str(error)[:240]
  return {'status':'NEEDS_REVIEW','summary':note,'issues':[note],'repair_assets':[],'asset_checks':[],'file_checks':[],'color_checks':[],'acceptance_checks':[]}

def gentle_glow(node):
 for key,opacity,size in [('outerGlow',.3,12),('innerGlow',.2,8)]:
  fx=node.get('layerStyle',{}).get(key) if node.get('layerStyle') else None
  if fx:
   fx['opacity']=min(fx.get('opacity',opacity),opacity);fx['size']=min(fx.get('size',size),size)

def preserve_native(scene,previous):
 for n in scene['nodes']:
  if n.get('sourceAssetId') and n.get('type')=='path':n.setdefault('sourceInkColor',n.get('fill'))
 if not previous:return
 def key(n):
  ident=n.get('sourceTextId') or n.get('sourceVectorId') or n.get('sourceAssetId') or n['id']
  ink=None
  if n.get('sourceAssetId') and n.get('type')=='path':
   suffix=re.search(r'#[0-9a-fA-F]{6}$',n.get('name',''))
   ink=n.get('sourceInkColor') or (suffix.group(0) if suffix else n.get('fill'))
  return (n['type'],ident,ink)
 candidates=[n for n in previous.get('nodes',[]) if n.get('type')!='image' and not n.get('reviewIssue') and not n.get('versionArchived')]
 from collections import Counter
 counts=Counter(key(n) for n in candidates)
 native={key(n):n for n in candidates if counts[key(n)]==1}
 for i,current in enumerate(scene['nodes']):
  old=native.get(key(current))
  if old:scene['nodes'][i]={**copy.deepcopy(old),'id':current['id']}
 groups={g['id']:g for g in previous.get('groups',[]) if not g.get('reviewIssue')}
 for g in scene.get('groups',[]):
  old=groups.get(g['id'])
  if old:
   for k in ('name','opacity','visible','locked','layerStyle','displayMask'):
    if k in old:g[k]=copy.deepcopy(old[k])

def remember_record(node,structure,background=False):
 file=Path(structure)/('背景补全来源.json' if background else '补全_'+node['id']+'.json')
 if file.is_file():
  record=json.loads(file.read_text('utf8'))
  if record.get('actualImageGeneration'):
   digest=hashlib.sha256(base64.b64decode(node['src'].split(',',1)[1],validate=True)).hexdigest()
   # A later failed attempt may have overwritten its record; never rewrite a
   # pre-existing SHA to pretend it describes an earlier retained candidate.
   if record.get('generatedAssetSHA256') not in (None,digest):return node
   if record.get('file') and hashlib.sha256(Path(record['file']).read_bytes()).hexdigest()!=digest:return node
   record.setdefault('generatedAssetSHA256',digest)
  node['generationRecord']={k:record[k] for k in ('actualImageGeneration','transparent','sourceOriginalSHA256','generatedAssetSHA256') if k in record}
 return node

def restore_asset(cached,current,assets,structure,source_sha,background=False):
 if not background and set(cached.get('sourceEntityParts',[]))!=set(current.get('sourceEntityParts',[])):raise ValueError('续拆实体成员已改变，需要提取完整新实体')
 record=copy.deepcopy(cached.get('generationRecord',{}))
 raw=base64.b64decode(cached['src'].split(',',1)[1],validate=True)
 if not record.get('actualImageGeneration') or record.get('sourceOriginalSHA256')!=source_sha or record.get('generatedAssetSHA256')!=hashlib.sha256(raw).hexdigest():raise ValueError('续拆素材与原图或登记字节不一致')
 from PIL import Image
 import io
 with Image.open(io.BytesIO(raw)) as im:
  if im.width*im.height>6000000:raise ValueError('续拆素材过大')
 result={**copy.deepcopy(cached),'id':current['id'],'name':current['name']}
 # Reuse the user's accepted object, including manual appearance edits; gentle
 # automatic styles apply only to newly planned/generated objects.
 file=Path(assets)/('续拆_'+current['id']+'.png');file.write_bytes(raw);record['file']=str(file)
 (Path(structure)/('背景补全来源.json' if background else '补全_'+current['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False),'utf8')
 return result

def extract_checked(source,node,assets,structure,cancelled,original,on_status):
 from workflow_assets import complete_asset
 from acceptance import review_asset
 candidate=None;quality=None;errors=[]
 for attempt in range(2):
  if cancelled():raise InterruptedError('已取消')
  try:
   generated=complete_asset(source,node,assets,structure,cancelled,original_source=original,force_repair=bool(attempt),on_status=on_status)
   candidate=generated
   quality=review_asset(source,candidate,structure,cancelled,on_status=on_status)
   if quality['status']=='PASS':
    candidate.update(assetReviewStatus='PASS',review=False);candidate.pop('reviewIssue',None);break
   node['_repairNotes']=quality['issues']
  except InterruptedError:raise
  except Exception as error:
   errors.append(str(error)[:240])
  if on_status:on_status('素材「'+node['name']+'」待校对，正在尝试修正…')
 if candidate is None:
  # Keep a clearly labelled source crop when this item could not be extracted.
  # It is never represented as a complete transparent ImageGen asset.
  from PIL import Image
  from engine import png
  with Image.open(source) as im:
   box=(max(0,int(node['x'])),max(0,int(node['y'])),min(im.width,int(node['x']+node['width'])),min(im.height,int(node['y']+node['height'])))
   crop=im.crop(box).convert('RGBA')
  candidate={**node,'src':png(crop),'x':box[0],'y':box[1],'width':crop.width,'height':crop.height,'provenance':'source-crop-fallback','inferred':False}
 if candidate.get('assetReviewStatus')!='PASS':
  issues=(quality or {}).get('issues',[])+errors
  candidate.update(assetReviewStatus='NEEDS_REVIEW',review=True,reviewIssue='；'.join(issues) or '素材尚未通过复核',assetReviewChecks=(quality or {}).get('checks',[]))
 if structure is not None:remember_record(candidate,structure)
 return candidate

def extract_once(source,node,assets,structure,cancelled,original,on_status):
 """First pass extracts once. Never claim visual approval or silently retry."""
 from workflow_assets import complete_asset
 if cancelled():raise InterruptedError('已取消')
 try:
  candidate=complete_asset(source,node,assets,structure,cancelled,original_source=original,on_status=on_status)
 except InterruptedError:raise
 except Exception as error:
  from PIL import Image
  from engine import png
  with Image.open(source) as im:
   box=(max(0,int(node['x'])),max(0,int(node['y'])),min(im.width,int(node['x']+node['width'])),min(im.height,int(node['y']+node['height'])))
   crop=im.crop(box).convert('RGBA')
  return {**node,'src':png(crop),'x':box[0],'y':box[1],'width':crop.width,'height':crop.height,'provenance':'source-crop-fallback','inferred':False,'assetReviewStatus':'NEEDS_REVIEW','review':True,'reviewIssue':'未能提取，保留原图区域：'+str(error)[:200]}
 candidate.update(assetReviewStatus='NOT_REVIEWED',review=True)
 candidate.pop('pendingGeneration',None)
 candidate.pop('reviewIssue',None)
 if structure is not None:remember_record(candidate,structure)
 return candidate

def check_resume_assets(source,scene,previous,assets,structure,source_sha,cancelled,on_status):
 """Legacy explicit-review helper; Continue must never invoke this function."""
 from acceptance import review_asset
 cached={n.get('sourceEntityId') or n.get('sourceAssetId') or n.get('id'):n for n in previous.get('nodes',[]) if n.get('type')=='image' and n.get('assetKind')!='background' and not n.get('versionArchived')}
 reusable={};repairs={};locked=effective_locked_ids(previous)
 for current in scene['nodes']:
  key=current.get('sourceEntityId') or current.get('sourceAssetId') or current.get('id')
  old=cached.get(key)
  if current.get('type')!='image' or current.get('versionArchived') or old is None:continue
  if cancelled():raise InterruptedError('已取消')
  try:candidate=restore_asset(old,current,assets,structure,source_sha)
  except (ValueError,KeyError):continue
  if old['id'] in locked:
   reusable[key]=candidate;continue
  if on_status:on_status('正在检查已有素材：'+current['name'])
  try:quality=review_asset(source,candidate,structure,cancelled,on_status=on_status)
  except InterruptedError:raise
  except Exception as error:
   candidate.update(assetReviewStatus='NEEDS_REVIEW',review=True,reviewIssue='续拆复核未完成，保留原素材：'+str(error)[:200])
   reusable[key]=candidate;continue
  if quality.get('status')=='PASS':
   candidate.update(assetReviewStatus='PASS',review=False);candidate.pop('reviewIssue',None);reusable[key]=candidate
  else:
   candidate.update(assetReviewStatus='NEEDS_REVIEW',review=True,reviewIssue='；'.join(quality.get('issues',[])) or '已有素材需要修正')
   repairs[key]=candidate
 return reusable,repairs

def check_resume_native(source,scene,cancelled,on_status):
 """Manual selected-layer review helper; separate from missing-only Continue."""
 from refine_ui import PATCHES,apply_patches
 from codex_client import CLIENT
 locked=effective_locked_ids(scene)
 editable=[{k:v for k,v in n.items() if k!='src'} for n in scene['nodes'] if n.get('type') in ('text','rect','ellipse','path') and n['id'] not in locked and not n.get('versionArchived')]
 if not editable:return scene
 if cancelled():raise InterruptedError('已取消')
 if on_status:on_status('正在检查已有文字与简单面板…')
 try:
  response=CLIENT.analyze('这是用户手动检查选中图层。依据原图检查所提供的原生文字和简单矢量参数，仅返回确有错误的修正；不要改图像、父组、顺序、ID、类型或蒙版。对照文案、字高字宽、方向、字号和面板位置；禁止横向拉伸、缩小正文、把普通字改成粗描边字、凭空新增投影/发光/叠加。未知字段填null，不确定则保留。所提供的是当前参数及原图，不是实际PSD回读，不宣称已经视觉验收通过。当前图层：'+json.dumps(editable,ensure_ascii=False),[source],PATCHES,cancelled,on_status=on_status)
  result,warnings=apply_patches(scene,response.get('patches'))
  result.setdefault('recognition',{}).setdefault('warnings',[]).extend(warnings+[n for n in response.get('notes',[]) if isinstance(n,str)])
  return result
 except InterruptedError:raise
 except Exception as error:
  scene.setdefault('recognition',{}).setdefault('warnings',[]).append('已有文字检查未完成，保留原参数：'+str(error)[:200])
  return scene
