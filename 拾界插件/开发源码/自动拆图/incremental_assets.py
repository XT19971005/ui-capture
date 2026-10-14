"""Partial quality findings do not discard usable work. Resume data stays in RAM."""
import base64,copy,hashlib,json,re
from pathlib import Path

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
 candidates=[n for n in previous.get('nodes',[]) if n.get('type')!='image' and not n.get('reviewIssue')]
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
