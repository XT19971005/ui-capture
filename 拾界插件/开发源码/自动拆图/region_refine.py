"""One regional diagnosis, with an explicit allowlist and bounded geometry."""
import base64,copy,io,json,math
from pathlib import Path
from PIL import Image


def validate_region(scene,region):
 if not isinstance(region,dict) or set(region)!={'x','y','width','height'}:raise ValueError('检查区域必须是画布内的矩形')
 for value in region.values():
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('检查区域坐标无效')
 x,y,w,h=(region[k] for k in ('x','y','width','height'))
 if x<0 or y<0 or w<=0 or h<=0 or x+w>scene.get('width',0) or y+h>scene.get('height',0):raise ValueError('检查区域必须完整位于画布内')
 return dict(region)


def contains(region,node):
 values=[node.get(k) for k in ('x','y','width','height')]
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):return False
 x,y,w,h=values
 return w>0 and h>0 and x>=region['x'] and y>=region['y'] and x+w<=region['x']+region['width'] and y+h<=region['y']+region['height']


def validate_targets(scene,ids,region):
 from incremental_assets import pending_generation
 validate_region(scene,region)
 entries={n['id']:n for n in [*scene['nodes'],*scene.get('groups',[])]}
 owner={child:g['id'] for g in scene.get('groups',[]) for child in g.get('children',[])}
 for ident in ids:
  node=entries[ident]
  if node.get('assetKind')=='background':raise ValueError('区域检查不自动重做整张背景，请选择具体前景图层')
  if pending_generation(node):raise ValueError('请先完成区域内所选素材的拆分')
  if not contains(region,node):raise ValueError('所选图层跨出检查区域，请扩大框选或取消该图层')
  seen=set();current=ident
  while current is not None:
   if current in seen:raise ValueError('区域分组包含循环引用')
   seen.add(current);entry=entries[current]
   if entry.get('locked') or entry.get('visible') is False or entry.get('hidden') or entry.get('versionArchived'):raise ValueError('区域检查仅允许可见、未锁定的当前图层')
   current=owner.get(current)


def diagnose(source,scene,selected,region,structure,cancelled,on_status):
 """The sheets are selected raster drafts, not a PSD or a full-scene audit."""
 from codex_client import CLIENT
 from refine_ui import PATCHES
 from acceptance import GRANULARITY_RULES
 from asset_geometry import PLACEMENT,PLACEMENT_PROMPT
 if cancelled():raise InterruptedError('已取消')
 schema={'type':'object','additionalProperties':False,'required':['assetChecks','patches','notes'],'properties':{
  'assetChecks':{'type':'array','maxItems':700,'items':{'type':'object','additionalProperties':False,'required':['id','status','issues'],'properties':{'id':{'type':'string'},'status':{'type':'string','enum':['PASS','FAIL','NEEDS_REVIEW']},'issues':{'type':'array','items':{'type':'string'}}}}},
  'patches':PATCHES['properties']['patches'],'notes':{'type':'array','maxItems':100,'items':{'type':'string'}}}}
 schema['properties']['assetChecks']['items']['properties']['placement']=PLACEMENT
 schema['properties']['assetChecks']['items']['required'].append('placement')
 x,y=math.floor(region['x']),math.floor(region['y']);right=math.ceil(region['x']+region['width']);bottom=math.ceil(region['y']+region['height'])
 folder=Path(structure);files=[]
 try:
  original=folder/'区域检查_原图.png'
  with Image.open(source) as im:im.convert('RGB').crop((x,y,right,bottom)).save(original)
  files.append(original)
  images=[n for n in selected if n['type']=='image']
  if images:
   drafts=Image.new('RGBA',(right-x,bottom-y))
   for node in images:
    if cancelled():raise InterruptedError('已取消')
    with Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1],validate=True))) as im:
     raster=im.convert('RGBA').resize((max(1,round(node['width'])),max(1,round(node['height']))),Image.Resampling.LANCZOS)
    drafts.alpha_composite(raster,(round(node['x']-x),round(node['y']-y)))
   for label,color in [('深底',(24,25,28,255)),('浅底',(240,240,240,255))]:
    file=folder/('区域检查_当前素材_'+label+'.png');sheet=Image.new('RGBA',drafts.size,color);sheet.alpha_composite(drafts);sheet.save(file);files.append(file)
  manifest=[{k:v for k,v in n.items() if k not in ('src','generationRecord')} for n in selected]
  prompt='用户明确框选区域检查。仅检查并提出所确认图层的必要修正，不检查整张工程，不新增图层，不修改名单外图层、父组、层级、ID、类型或背景。区域 ROI（原画布绝对坐标）：'+json.dumps(region,ensure_ascii=False)+'；原画布尺寸：'+json.dumps({'width':scene['width'],'height':scene['height']})+'。第一张是原图 ROI 裁图，裁图像素原点对应绝对坐标 '+json.dumps({'x':x,'y':y})+'。后两张（如有）是仅所选图片素材按原位置叠放在深浅底的当前完整底稿，未加入未选图层、原生文字矢量、蒙版或样式，不是完整当前画面或实际 PSD 回读。不要把这些刻意省略的内容判成素材缺陷；遮挡、样式或原生渲染证据不足时保留并在 notes 说明，不得盲目 PASS。原生文字/矢量依据原图裁图和当前参数检查。返回每个所选 image 唯一的 assetChecks，只有明确错误才 FAIL；对原生文字/矢量返回必要 patches，参数仍使用原画布绝对坐标，未知字段 null，不改变类型/ID/遮罩，不添加效果。修正后的完整图层框必须仍完全位于 ROI。不能把框外工程问题混入 notes，不要求全图复检。'+GRANULARITY_RULES+'\n已确认图层（唯一允许范围）：'+json.dumps(manifest,ensure_ascii=False)
  prompt+='\n'+PLACEMENT_PROMPT+'\n本次为区域检查，placement必须完整位于用户确认区域内。'
  result=CLIENT.analyze(prompt,files,schema,cancelled,on_status=on_status)
  if cancelled():raise InterruptedError('已取消')
  image_ids={n['id'] for n in images};native_ids={n['id'] for n in selected if n['type'] in ('text','rect','ellipse','path')}
  if not isinstance(result,dict) or set(result)!={'assetChecks','patches','notes'}:raise ValueError('区域诊断结构无效')
  checks=result['assetChecks'];patches=result['patches'];notes=result['notes']
  if not isinstance(checks,list) or len(checks)!=len(image_ids) or any(not isinstance(c,dict) or c.get('id') not in image_ids for c in checks) or {c['id'] for c in checks}!=image_ids:raise ValueError('区域诊断包含未确认图层或缺少所选图层')
  for check in checks:
   if check.get('status') not in ('PASS','FAIL','NEEDS_REVIEW') or not isinstance(check.get('issues'),list) or any(not isinstance(i,str) or len(i)>2000 for i in check['issues']):raise ValueError('区域素材诊断无效')
   if check['status']=='PASS' and check['issues']:check['status']='NEEDS_REVIEW'
  if not isinstance(patches,list) or len(patches)>len(native_ids) or any(not isinstance(p,dict) or p.get('id') not in native_ids for p in patches) or len({p['id'] for p in patches})!=len(patches):raise ValueError('区域修正包含未确认的原生图层')
  if not isinstance(notes,list) or len(notes)>100 or any(not isinstance(n,str) or len(n)>2000 for n in notes):raise ValueError('区域诊断说明无效')
  return result
 finally:
  for file in files:file.unlink(missing_ok=True)
