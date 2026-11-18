"""Complete semantic assets on an expanded, registered canvas; never fit into an old box."""
import math,hashlib,base64
from pathlib import Path
from PIL import Image

def register_asset(target,reference_side,origin):
 """Preserve returned pixels; registration is a separate, explicitly reviewed transform."""
 raw=Path(target).read_bytes()
 with Image.open(target) as im:
  im.load()
  if im.mode!='RGBA' or im.getchannel('A').getextrema()[0]!=0:raise ValueError('生成素材没有真实透明通道')
  box=im.getchannel('A').getbbox()
  if not box:raise ValueError('生成素材为空透明图片')
  if max(im.size)>6000 or im.width*im.height>36000000:raise ValueError('生成素材原始像素超过当前上限；没有缩小或裁切')
  width,height=im.size
  # A faint glow/noise pixel is not evidence that the object's shape was cut.
  # This mask is used for review only; original PNG/low-alpha pixels are untouched.
  visible=im.getchannel('A').point(lambda value:255 if value>=16 else 0).getbbox()
  edge=bool(visible and (visible[0]==0 or visible[1]==0 or visible[2]==width or visible[3]==height))
 rw,rh=(reference_side,reference_side) if isinstance(reference_side,(int,float)) else reference_side
 scale=min(rw/width,rh/height)
 mismatch=abs((width/height)/(rw/rh)-1)>.001
 issues=[]
 if mismatch:issues.append('返回画幅与参考不同，保留原比例；当前位置为临时登记，请对照原图调整')
 if edge:issues.append('生成素材触及图片边缘，可能不完整；原始像素已保留，需检查或返修')
 return {'src':'data:image/png;base64,'+base64.b64encode(raw).decode('ascii'),
  'x':origin[0]+(rw-width*scale)/2,'y':origin[1]+(rh-height*scale)/2,
  'width':width*scale,'height':height*scale,'positionReviewRequired':mismatch,'boundaryReviewRequired':edge,
  'reviewIssue':'；'.join(issues),'registration':{'method':'reference-center-provisional' if mismatch else 'reference-canvas','scale':scale,'rawWidth':width,'rawHeight':height}}

def extract(source,layer,assets,cancelled,on_status,annotations=None,structure=None):
 from image_provider import CLIENT,settings
 from reference_fidelity import COLOR_PRESERVATION
 with Image.open(source) as raw:original=raw.convert('RGBA')
 w,h=original.size
 from asset_resolution import prepare_reference,resolution_prompt,apply_resolution,pad_reference_minimum
 reference=assets/(layer['id']+'_高清局部参考.png')
 target=assets/(layer['id']+'_完整扩展.png')
 config=settings();allowed_ratios=None
 if config.get('provider')=='aimake':
  from image_provider import model_schema
  props=model_schema(config['model']).get('input',{}).get('properties',{})
  allowed_ratios=[] if config['model'].startswith('gpt-image-') and 'width' in props and 'height' in props else props.get('aspect_ratio',{}).get('enum')
 frame=prepare_reference(original,layer,reference,allowed_ratios=allowed_ratios)
 rw,rh=frame['sourceCanvasSize']
 prompt=COLOR_PRESERVATION+'只提取并补全指定独立部件：'+layer['extractionBrief']+'。'+resolution_prompt(frame)
 if layer.get('layerStyle'):prompt+='外挂投影、发光与描边另由原生图层样式重建，不烘焙进底稿；主体内部材质光照保留。'
 if layer.get('_otherLayers'):prompt+='其它对象仅供排除，不混入当前主体：'+'；'.join(str(item.get('name','')) for item in layer['_otherLayers'])
 prompt+='第一张是高清局部参考，第二张是完整干净原图；以原图的外观和比例为准，额外标注图仅供定位。'
 images=[reference,Path(source)];repair_reference=None;context_reference=None;marked_reference=None
 nano=config.get('provider')=='aimake' and config.get('model','').startswith('nano-banana')
 try:
  if nano:
   context_reference=assets/(layer['id']+'_全图上下文参考.png')
   if pad_reference_minimum(source,context_reference):
    images[1]=context_reference
    prompt+='第二张原图语义参考仅补透明留白以满足模型最小尺寸，原像素没有缩放；新增留白不是主体或输出布局。'
  if annotations and any(item.get('strokes') for item in annotations.get('items',[])):
   from source_annotations import render,summary
   import json
   marked_reference=assets/(layer['id']+'_标注定位参考.png')
   render(annotations,source,marked_reference)
   if nano:pad_reference_minimum(marked_reference,marked_reference)
   images.append(marked_reference)
   prompt+='带编号与彩色标线的图是定位参考，仅解释目标归属和原图中的范围，不是成品外观，也不是完整形体的裁切边界。目标为'+layer['name']+'。原有可见形状、光影和比例依据前两张干净参考；只补全遮挡或出画的缺失部分，不把标线、编号、文字或其它对象生成进去。标注说明：'+json.dumps(summary(annotations),ensure_ascii=False)
  elif structure is not None:
   from source_annotations import append_reference
   prompt,images=append_reference(prompt,images,structure)
  if layer.get('_repairSource'):
   prior=layer['_repairSource']
   if not isinstance(prior,str) or not prior.startswith('data:image/png;base64,') or len(prior)>36000000:raise ValueError('返修底稿无效')
   repair_reference=assets/(layer['id']+'_返修底稿参考.png');repair_reference.write_bytes(base64.b64decode(prior.split(',',1)[1],validate=True))
   if nano:pad_reference_minimum(repair_reference,repair_reference)
   images.append(repair_reference)
   prompt+='最后一张是本次返修前的完整底稿，只修复已经指出的问题，保留正确身份、姿势及已补全结构；仍按高清独立画幅输出，不把旧低分辨率直接放大冒充新细节。'
  if nano and repair_reference and marked_reference:
   ref_key=next((key for key in ('input_images','ref_images') if key in props),None)
   maximum=props.get(ref_key,{}).get('maxItems',3 if config['model']=='nano-banana' else 14)
   if len(images)>maximum:
    # Keep the clean target, marked full context and repair asset when the model accepts three references.
    images.pop(1)
  record=CLIENT.generate(prompt,images,target,transparent=True,cancelled=cancelled,on_status=on_status,allow_identity_change=False)
 finally:
  reference.unlink(missing_ok=True)
  if repair_reference:repair_reference.unlink(missing_ok=True)
  if context_reference:context_reference.unlink(missing_ok=True)
  if marked_reference:marked_reference.unlink(missing_ok=True)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('扩展素材未完成实际生成')
 registered=register_asset(target,(rw,rh),frame['sourceOrigin'])
 if not all(k in layer for k in ('x','y','width','height')):
  registered.update(positionReviewRequired=True,reviewIssue='；'.join(filter(None,[registered.get('reviewIssue'),'未提供目标几何，使用整张原图识别独立主体；当前仅为临时登记，请预览校对大小与位置'])))
 from asset_registration import calibrate
 if on_status:on_status('正在自动校对素材大小与位置…')
 registered=calibrate(source,registered,layer) if all(k in layer for k in ('x','y','width','height')) else registered
 if registered.get('registration',{}).get('status')!='aligned' and all(k in layer for k in ('x','y','width','height')) and layer['width']*layer['height']<w*h*.8:
  from semantic_registration import calibrate_semantic
  try:
   with Image.open(source) as original_image,Image.open(target) as generated_image:
    registered=calibrate_semantic(original_image.convert('RGB'),generated_image.convert('RGBA'),layer,registered,cancelled=cancelled,on_status=on_status)
  except Exception as exc:
   if isinstance(exc,InterruptedError) or cancelled():raise
   # Keep the valid paid PNG even if optional placement estimation fails.
   # Cancellation remains an explicit interruption, never a successful delivery.
   try:
    from asset_registration import annotation_estimate
    with Image.open(source) as check_source:
     region=check_source.convert('RGBA').crop((round(layer['x']),round(layer['y']),round(layer['x']+layer['width']),round(layer['y']+layer['height'])))
     has_reference=region.getchannel('A').getbbox() is not None
    if has_reference:
     with Image.open(target) as estimate_image:registered=annotation_estimate(estimate_image.convert('RGBA'),layer,registered)
     registered['registration']['detail']=str(exc)[:240]
     note='大小位置已按对应标注等比估算；仍需校对，不代表精确匹配'
    else:
     registered['positionReviewRequired']=True
     note='原图目标区域没有可见内容，保留完整素材及原参考落位'
   except Exception as estimate_error:
    if isinstance(estimate_error,InterruptedError) or cancelled():raise
    registered['positionReviewRequired']=True
    registered['registration']={**registered.get('registration',{}),'status':'needs-review','reason':'自动位置校对未完成','detail':str(estimate_error)[:240]}
    note='自动位置校对未完成，保留已生成完整PNG及临时落位：'+str(estimate_error)[:240]
   registered['reviewIssue']='；'.join(filter(None,[registered.get('reviewIssue'),note]))

 record['independentAssetRequest']={'referenceWidth':frame['referenceWidth'],'referenceHeight':frame['referenceHeight'],'referenceSide':max(frame['referenceWidth'],frame['referenceHeight']),'minimumSubjectLongEdge':1024,'referenceUpscaleOnly':True}
 registered=apply_resolution(registered,target,record)
 src=registered['src']
 return {'id':layer['id'],'name':layer['name'],'type':'image',**registered,'provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','assetKind':'complete-asset','assetReviewStatus':'NEEDS_REVIEW' if registered['reviewIssue'] else 'NOT_REVIEWED','review':True,'generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'generatedAssetSHA256':hashlib.sha256(base64.b64decode(src.split(',',1)[1])).hexdigest(),'expandedCanvas':True,**{k:record[k] for k in ('provider','model','genId','postprocessing','assetResolution','independentAssetRequest') if k in record}}}
