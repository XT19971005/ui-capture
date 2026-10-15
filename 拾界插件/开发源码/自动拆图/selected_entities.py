"""Joint selected-entity diagnosis and bounded native/bitmap assembly.

Membership is a visual model decision with explicit evidence, never a bbox or
name/color-count heuristic. The original leaf IDs remain valid for history.
"""
import base64,copy,datetime,hashlib,json,math,shutil,subprocess,uuid
from pathlib import Path
from PIL import Image
from design_properties import obj,nullable,NUMBER,COLOR,GRADIENT,color,gradient

ENTITY=obj({'members':{'type':'array','minItems':2,'maxItems':700,'items':{'type':'string'}},'name':{'type':'string'},'kind':{'type':'string','enum':['lettermark','character','icon','object']},'mode':{'type':'string','enum':['single-path','vector-group','image-union']},'confidence':NUMBER,'evidence':{'type':'string'},'contentCorrect':{'type':'boolean'},'fill':nullable(COLOR),'gradient':nullable(GRADIENT),'d':nullable({'type':'string'})})

def bounds(nodes):
 x=min(n['x'] for n in nodes);y=min(n['y'] for n in nodes)
 return {'x':x,'y':y,'width':max(n['x']+n['width'] for n in nodes)-x,'height':max(n['y']+n['height'] for n in nodes)-y}

def kernel(request):
 run=subprocess.run([shutil.which('node') or 'node',str(Path(__file__).with_name('selected_entity_native.cjs'))],input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,encoding='utf8',timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if run.returncode:raise ValueError('选集原生证据构建失败：'+run.stderr[-300:])
 return json.loads(run.stdout)

def diagnose(source,scene,selected,structure,cancelled,on_status,region=None):
 from codex_client import CLIENT
 from refine_ui import PATCHES
 from region_refine import contains
 if cancelled():raise InterruptedError('已取消')
 scope=region or bounds(selected);x=math.floor(scope['x']);y=math.floor(scope['y']);right=math.ceil(scope['x']+scope['width']);bottom=math.ceil(scope['y']+scope['height']);box={'x':x,'y':y,'width':right-x,'height':bottom-y}
 folder=Path(structure);prefix=folder/'联合选集';files=[folder/'联合选集_原图.png',Path(str(prefix)+'-dark.png'),Path(str(prefix)+'-light.png')]
 ids={n['id'] for n in selected};image_ids={n['id'] for n in selected if n['type']=='image'};native_ids=ids-image_ids;retained=set(ids);kept=[]
 for _ in scene.get('groups',[]):
  for g in scene.get('groups',[]):
   if any(i in retained for i in g['children']):retained.add(g['id'])
 for g in scene.get('groups',[]):
  if g['id'] in retained:kept.append({**copy.deepcopy(g),'children':[i for i in g['children'] if i in retained]})
 subset={'format':'shijie-scene','version':2,'title':'选集联合检查草图','width':scene['width'],'height':scene['height'],'nodes':copy.deepcopy(selected),'groups':kept,'edges':[]}
 check_id={'type':'string',**({'enum':sorted(image_ids)} if image_ids else {})}
 checks=obj({'id':check_id,'status':{'type':'string','enum':['PASS','FAIL','NEEDS_REVIEW']},'issues':{'type':'array','items':{'type':'string'}}})
 schema=obj({'entities':{'type':'array','maxItems':350,'items':ENTITY},'assetChecks':{'type':'array','minItems':len(image_ids),'maxItems':len(image_ids),'items':checks},'patches':PATCHES['properties']['patches'],'notes':{'type':'array','maxItems':100,'items':{'type':'string'}}})
 try:
  with Image.open(source) as im:im.convert('RGB').crop((x,y,right,bottom)).save(files[0])
  kernel({'operation':'preview','scene':subset,'box':box,'prefix':str(prefix)})
  manifest=[]
  for n in selected:
   item={k:v for k,v in n.items() if k not in ('src','generationRecord')}
   if len(item.get('d',''))>2400:item['d']='[原生路径长度 '+str(len(item['d']))+'；完整轮廓见当前选集图]'
   manifest.append(item)
  prompt='用户明确要求联合检查这些所选对象。先依据原图和整个当前选集判断完整语义实体，再联合修正；禁止逐色块各自修、只给错误色块套组就宣称修好。第一张是原图裁图，后两张是仅所选图层连同祖组蒙版/样式的实际SVG草图深浅底，不是PSD或整图验收。裁图原点='+json.dumps({'x':x,'y':y})+'。所有参数仍用画布绝对坐标。允许范围='+json.dumps(scope)+'。一体书法字标/角色/图标即使按色或局部拆成数层，也须作为一个完整实体判断；不同物体不因同框、重叠、同色或同名合并。同sourceVectorId/原规划实体仅是线索，必须对照原图证明。entities只列确信度>=0.9且有具体视觉证据的联合实体，独立/不确定者不列。single-path仅用于原图可用单一填色/原生渐变的同一完整轮廓，提供真实fill/gradient；d=null仅当现有各部分合起来的完整轮廓已正确、可原生布尔并集；轮廓错误须给联合完整替换d（相对实体联合框），不能拼凑残片。确实多色才vector-group，并用patches联合修复各原生色区；若contentCorrect=false而未给可实施的内容修正，必须保留待校对，不能靠group冒充修复。图片碎片用image-union只调用一次完整实体提取；范围外一律不处理。不得把普通文字栅格化或矢量改位图，不得新增未观察的效果。assetChecks对每个所选image各一条；patches仅列所选原生叶层，未知参数null。所有新结果仍需复核，不宣称视觉PASS。当前对象='+json.dumps(manifest,ensure_ascii=False)
  prompt+='\nassetChecks 图片检查唯一 ID 白名单='+json.dumps(sorted(image_ids),ensure_ascii=False)+'；每个图片 ID 恰好一条，其他 ID 禁止出现。原生文字/矢量 ID='+json.dumps(sorted(native_ids),ensure_ascii=False)+'，只允许用于 entities/patches，不得填入 assetChecks。'+('本次没有图片，assetChecks 必须为 []。' if not image_ids else '')
  result=CLIENT.analyze(prompt,files,schema,cancelled,on_status=on_status)
  if cancelled():raise InterruptedError('已取消')
  if not isinstance(result,dict) or set(result)!={'entities','assetChecks','patches','notes'}:raise ValueError('联合诊断结构无效')
  if not isinstance(result['entities'],list) or len(result['entities'])>350:raise ValueError('联合实体清单无效')
  used=set()
  for e in result['entities']:
   if not isinstance(e,dict) or set(e)!=set(ENTITY['properties']):raise ValueError('联合实体结构无效')
   members=e['members']
   if not isinstance(members,list) or len(members)<2 or len(members)!=len(set(members)) or not set(members)<=ids or used&set(members):raise ValueError('联合实体包含未选或重复图层')
   used.update(members)
   if e['mode'] not in ('single-path','vector-group','image-union') or e['kind'] not in ('lettermark','character','icon','object') or not isinstance(e['contentCorrect'],bool):raise ValueError('联合实体类型无效')
   if isinstance(e['confidence'],bool) or not isinstance(e['confidence'],(int,float)) or not math.isfinite(e['confidence']) or not 0<=e['confidence']<=1:raise ValueError('联合实体置信度无效')
   if not isinstance(e['evidence'],str) or not isinstance(e['name'],str) or not e['name'].strip() or len(e['name'])>120 or len(e['evidence'])>2000:raise ValueError('联合实体证据无效')
  rows=result['assetChecks']
  if not isinstance(rows,list) or any(not isinstance(c,dict) or set(c)!={'id','status','issues'} or not isinstance(c['id'],str) for c in rows):raise ValueError('联合图片检查格式无效：应有 '+str(len(image_ids))+' 个图片检查对象')
  returned=[c['id'] for c in rows];missing=sorted(image_ids-set(returned));foreign=sorted(set(returned)-image_ids)
  if len(rows)!=len(image_ids) or missing or foreign:
   details=['应有 '+str(len(image_ids))+' 个图片，收到 '+str(len(rows))+' 条']
   if foreign:details.append('非图片或未选 ID：'+', '.join(i[:48] for i in foreign[:3]))
   if missing:details.append('遗漏图片 ID：'+', '.join(i[:48] for i in missing[:3]))
   if len(returned)!=len(set(returned)):details.append('图片 ID 重复')
   raise ValueError('联合图片检查名单不符（'+'；'.join(details)+'）')
  if any(c['status'] not in ('PASS','FAIL','NEEDS_REVIEW') or not isinstance(c['issues'],list) or any(not isinstance(i,str) or len(i)>2000 for i in c['issues']) for c in rows):raise ValueError('联合图片检查状态或问题说明无效')
  for c in rows:
   if c['status']=='PASS' and c['issues']:c['status']='NEEDS_REVIEW'
  patches=result['patches']
  if not isinstance(patches,list) or len(patches)>len(native_ids) or any(not isinstance(p,dict) or p.get('id') not in native_ids for p in patches) or len({p['id'] for p in patches})!=len(patches):raise ValueError('联合原生修正越过选集')
  if not isinstance(result['notes'],list) or len(result['notes'])>100 or any(not isinstance(n,str) or len(n)>2000 for n in result['notes']):raise ValueError('联合诊断说明无效')
  return result
 finally:
  for file in files:file.unlink(missing_ok=True)

def sibling_span(scene,parent,members):
 """Hidden archived leaves do not split active siblings, but retain their slots."""
 nodes={n['id']:n for n in scene['nodes']};groups={g['id']:g for g in scene.get('groups',[])}
 if parent:siblings=groups[parent]['children']
 else:
  owner={i:g['id'] for g in groups.values() for i in g['children']};siblings=[]
  for n in scene['nodes']:
   root=n['id']
   while root in owner:root=owner[root]
   if root not in siblings:siblings.append(root)
 def archived(ident):
  n=nodes.get(ident,{})
  # Match S.layerHidden: explicit visibility overrides the legacy hidden flag.
  return n.get('versionArchived') is True and (n.get('visible') is False or 'visible' not in n and n.get('hidden') is True)
 current=[i for i in siblings if not archived(i)];positions=sorted(current.index(i) for i in members)
 if positions!=list(range(positions[0],positions[-1]+1)):raise ValueError('联合实体与其他图层交错，不能改变未选层顺序')
 ordered=[i for i in current if i in set(members)]
 return ordered,siblings[siblings.index(ordered[0]):siblings.index(ordered[-1])+1]

def eligible(scene,entity):
 """Reject a tree-changing proposal before any repair or paid extraction."""
 members=entity['members'];nodes={n['id']:n for n in scene['nodes']};groups={g['id']:g for g in scene.get('groups',[])};owner={i:g['id'] for g in groups.values() for i in g['children']}
 if entity['confidence']<.9 or len(entity['evidence'].strip())<8:raise ValueError('原图语义证据不足，保留原层')
 parent=owner.get(members[0])
 if any(owner.get(i)!=parent for i in members):raise ValueError('联合实体跨父组，不能无损合并')
 ordered,_=sibling_span(scene,parent,members);parts=[nodes[i] for i in ordered]
 if any(n.get('assetKind')=='background' or n.get('versionArchived') or n.get('visible') is False or n.get('hidden') for n in parts):raise ValueError('背景、隐藏层及历史层不参与实体合并')
 kinds={n['type'] for n in parts};mode=entity['mode']
 if mode=='single-path' and kinds!={'path'} or mode=='vector-group' and not kinds<={'path','rect','ellipse'} or mode=='image-union' and kinds!={'image'}:raise ValueError('不能把原生文字、矢量与图片跨类型合并')
 if mode!='vector-group':
  if any(n.get('displayMask') or n.get('layerStyle') or n.get('gradient') or n.get('opacity',1)!=1 or n.get('blendMode','normal')!='normal' or n.get('rotation',0) or n.get('strokeWidth',0) for n in parts):raise ValueError('所选部分带有独立蒙版或效果，不能丢失这些外观设置')
  consumed=set(ordered[1:])
  if any(e.get('from') in consumed or e.get('to') in consumed for e in scene.get('edges',[])):raise ValueError('所选部分存在独立连线，不能隐藏其端点')
 return parts,parent,bounds(parts)

def apply(scene,original_scene,entity,structure,source,original_file,assets,cancelled,on_status,extract_once,region=None):
 from region_refine import contains
 from refine_ui import _path_inside
 parts,parent,box=eligible(scene,entity);members=[n['id'] for n in parts];anchor=parts[0];mode=entity['mode'];old={n['id']:n for n in original_scene['nodes']};result=copy.deepcopy(scene);by_id={n['id']:n for n in result['nodes']}
 if mode=='vector-group':
  painted=('x','y','width','height','d','fill','stroke','strokeWidth','radius','gradient','layerStyle','displayMask','opacity','blendMode')
  if not entity['contentCorrect'] and not any(any(by_id[i].get(k)!=old[i].get(k) for k in painted) for i in members):raise ValueError('实体内容仍错误但没有联合内容修正，不能仅套分组冒充修复')
  _,span=sibling_span(scene,parent,members)
  group={'id':'entity-'+uuid.uuid4().hex,'name':entity['name'],'children':span,'semanticEntityKind':entity['kind'],'semanticEntityMembers':members,'semanticEvidence':entity['evidence'],'review':True};result.setdefault('groups',[]).append(group)
  if parent:
   g=next(g for g in result['groups'] if g['id']==parent);first=g['children'].index(members[0]);g['children'][first:first+len(span)]=[group['id']]
  selected_id=group['id'];group_id=group['id']
 else:
  candidate={**copy.deepcopy(anchor),'name':entity['name'],**box,'review':True,'assetReviewStatus':'NOT_REVIEWED','semanticEntityKind':entity['kind'],'semanticEntityMembers':members,'semanticEvidence':entity['evidence']}
  if mode=='single-path':
   if entity['d'] is None:
    if not entity['contentCorrect']:raise ValueError('轮廓不正确却没有联合完整替换路径')
    candidate['d']=kernel({'operation':'union','nodes':parts,'box':box})['d']
   else:candidate['d']=entity['d']
   candidate['fill']=color(entity['fill']);candidate.pop('gradient',None)
   if entity['gradient'] is not None:candidate['gradient']=gradient(entity['gradient'])
   _path_inside(candidate)
  else:
   # Source crop is the entire allowed entity frame, so the existing extractor
   # cannot pad its request into unselected neighbouring content.
   allowed=box;left=math.floor(box['x']);top=math.floor(box['y']);right=math.ceil(box['x']+box['width']);bottom=math.ceil(box['y']+box['height']);roi=Path(structure)/('联合实体_'+uuid.uuid4().hex+'.png')
   with Image.open(source) as im:im.crop((left,top,right,bottom)).save(roi)
   local={**candidate,'x':0,'y':0,'width':right-left,'height':bottom-top,'sourceEntityId':'selected-entity-'+uuid.uuid4().hex,'sourceEntityParts':sorted({part for n in parts for part in n.get('sourceEntityParts',[n.get('sourceAssetId') or n['id']])}),'_repairNotes':['仅提取同一完整实体，所有成员共同构成一体：'+', '.join(n['name'] for n in parts),'保持原图身份、颜色、完整轮廓及孔洞；不得处理ROI外任何物体。',entity['evidence']]};local.pop('generationRecord',None)
   try:generated=extract_once(roi,local,assets,structure,cancelled,original_file,on_status)
   finally:roi.unlink(missing_ok=True)
   if generated.get('provenance')=='source-crop-fallback':raise ValueError('完整实体提取未完成，保留全部旧部分')
   if generated.get('id')!=anchor['id'] or generated.get('type')!='image' or not contains({'x':0,'y':0,'width':right-left,'height':bottom-top},generated):raise ValueError('完整实体提取越过所选范围或改变身份')
   scale=min(allowed['width']/(right-left),allowed['height']/(bottom-top));candidate={**generated,'x':allowed['x']+(allowed['width']-(right-left)*scale)/2+generated['x']*scale,'y':allowed['y']+(allowed['height']-(bottom-top)*scale)/2+generated['y']*scale,'width':generated['width']*scale,'height':generated['height']*scale,'semanticEntityKind':entity['kind'],'semanticEntityMembers':members,'semanticEvidence':entity['evidence'],'assetReviewStatus':'NOT_REVIEWED','review':True};candidate.pop('_repairNotes',None)
  if not contains(box,candidate) or region is not None and not contains(region,candidate):raise ValueError('联合结果越出所选实体范围')
  by_id[anchor['id']].clear();by_id[anchor['id']].update(candidate)
  for ident in members[1:]:
   by_id[ident].clear();by_id[ident].update(copy.deepcopy(old[ident]));by_id[ident].update(visible=False,hidden=True,versionArchived=True,versionOf=anchor['id'],versionArchivedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
  selected_id=anchor['id'];group_id=None
 operation={'mode':mode,'members':members,'anchorId':anchor['id'],'groupId':group_id,'parentId':parent,'kind':entity['kind'],'evidence':entity['evidence'],'confidence':entity['confidence']}
 return result,operation,selected_id

def validate_structure(before,after,operations,selected_ids):
 """Only declared adjacent selected siblings may acquire an identity wrapper."""
 expected=copy.deepcopy(before.get('groups',[]));nodes={n['id']:n for n in before['nodes']};selected=set(selected_ids);used=set()
 for op in operations:
  if not set(op['members'])<=selected or used&set(op['members']):raise ValueError('联合修改越过选集')
  used.update(op['members'])
  if op['mode']=='vector-group':
   actual=next((g for g in after.get('groups',[]) if g['id']==op['groupId']),None)
   _,span=sibling_span(before,op['parentId'],op['members'])
   if not actual or actual['children']!=span or set(actual)-{'id','name','children','semanticEntityKind','semanticEntityMembers','semanticEvidence','review'}:raise ValueError('联合实体分组无效')
   if op['parentId']:
    parent=next(g for g in expected if g['id']==op['parentId']);at=parent['children'].index(op['members'][0]);parent['children'][at:at+len(span)]=[op['groupId']]
   expected.append(copy.deepcopy(actual))
 if expected!=after.get('groups',[]):raise ValueError('联合修正改变了未声明的父组或蒙版')
