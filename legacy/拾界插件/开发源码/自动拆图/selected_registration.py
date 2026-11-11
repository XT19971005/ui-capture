"""Re-run generation registration for exactly one existing raster layer."""
import copy, math
from asset_registration import calibrate
from image_replace import _image

def process(value):
 if not isinstance(value,dict) or set(value)!={'scene','targetId'}:raise ValueError('校对参数无效')
 scene=value['scene'];ident=value['targetId']
 if not isinstance(scene,dict) or not isinstance(scene.get('nodes'),list):raise ValueError('工程无效')
 matches=[n for n in scene['nodes'] if n.get('id')==ident]
 if len(matches)!=1:raise ValueError('请选择一张图片')
 node=matches[0]
 if node.get('type')!='image' or node.get('locked') or node.get('versionArchived') or node.get('provenance')=='source-reference':raise ValueError('请选择未锁定的素材图片')
 targets=scene.get('recognition',{}).get('requestedLayers',[])
 targets=[t for t in targets if (t.get('id') and (t.get('id')==node.get('sourceAssetId') or t.get('id')==ident))] or [t for t in targets if t.get('name')==node.get('name')]
 if len(targets)!=1:raise ValueError('无法唯一对应原图标注，未修改图片')
 target=targets[0].get('box',{})
 if not all(isinstance(target.get(k),(int,float)) and math.isfinite(target[k]) for k in ('x','y','width','height')) or min(target['width'],target['height'])<=0:raise ValueError('原图标注范围无效')
 # Match boxes in their original generation coordinates, not the padded canvas.
 schedule=scene.get('_generationStages') or {};scope=schedule.get('scope') or {}
 source=scope.get('image') or scene.get('comparisonSource') or scene.get('source')
 if not isinstance(source,str) or not source.startswith('data:image/'):raise ValueError('缺少原图')
 from asset_registration import annotation_estimate
 from semantic_registration import calibrate_semantic
 with _image(source) as raw, _image(node['src']) as generated:
  image=raw.convert('RGB');ox=oy=0;scale=1;crop_x=crop_y=0
  if scope.get('image'):
   ox=float(schedule.get('dx',0));oy=float(schedule.get('dy',0))
   parent=scope.get('node')
   if parent:
    scale=float(parent['width'])/scope['width'];ox+=parent['x'];oy+=parent['y']
  else:
   frame=scene.get('recognition',{}).get('sourceFrame') or {}
   if frame.get('width') and frame.get('height'):
    ox=float(frame.get('x',0));oy=float(frame.get('y',0));fw=float(frame['width']);fh=float(frame['height'])
    if abs(image.width-scene.get('width',0))<1 and abs(image.height-scene.get('height',0))<1:
     image=image.crop((round(ox),round(oy),round(ox+fw),round(oy+fh)));crop_x=ox;crop_y=oy
    else:
     scale=fw/image.width
     if abs(scale-fh/image.height)>1e-5:raise ValueError('原图坐标比例不一致，未修改图片')
  if targets[0].get('assetKind')=='background' or node.get('assetKind')=='background':
   from asset_registration import background_frame
   alpha=raw.convert('RGBA').getchannel('A');content=alpha.point(lambda v:255 if v>=128 else 0).getbbox()
   if content is None:raise ValueError('原图没有可识别的有效画幅，未修改背景')
   l,t,r,b=content;result=background_frame(generated,(l-crop_x,t-crop_y,r-l,b-t),node)
  else:
   result=calibrate(image,node,target)
   if result.get('registration',{}).get('status')!='aligned':
    try:result=calibrate_semantic(image,generated,{**target,'name':node.get('name')},node)
    except (ValueError,RuntimeError) as exc:
     result=annotation_estimate(generated,target,node);result['registration']['detail']=str(exc)[:240]
  result.update(x=result['x']*scale+ox,y=result['y']*scale+oy,width=result['width']*scale,height=result['height']*scale)
  result['registration']['sourceMapping']={'x':ox,'y':oy,'scale':scale}
 # Return only placement fields; never replace image bytes, styles, or other layers.
 return {'targetId':ident,'placement':{k:result[k] for k in ('x','y','width','height')},'registration':result['registration']}
