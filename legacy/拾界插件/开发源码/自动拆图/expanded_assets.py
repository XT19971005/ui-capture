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

def extract(source,layer,assets,cancelled,on_status,annotations=None):
 from image_provider import CLIENT,settings
 from reference_fidelity import COLOR_PRESERVATION
 from engine import png
 with Image.open(source) as raw:original=raw.convert('RGBA')
 w,h=original.size
 from expansion_geometry import margins
 info=assets.parent/'02_结构/用户原画标注.json'
 marked_state=None
 if info.is_file():
  import json
  marked_state=json.loads(info.read_text('utf8'))
 allow_outside=bool(annotations and annotations.get('allowExpand') is True) or bool(isinstance(marked_state,dict) and marked_state.get('allowExpand') is True)
 budget=36000000
 if allow_outside:
  from source_annotations import mark_margins
  mx,my=mark_margins(w,h)
 else:
  try:mx,my=margins(w,h,max_pixels=budget)
  except ValueError:
   bounds=original.getchannel('A').getbbox()
   if bounds and (bounds[0]>0 or bounds[1]>0 or bounds[2]<w or bounds[3]<h):mx=my=0
   else:raise
  limit=min(6000,math.isqrt(budget))
  if max(w,h)<limit:
   mx=min(mx,(limit-w)//2);my=min(my,(limit-h)//2)
 ew,eh=w+2*mx,h+2*my
 if max(ew,eh)>6000 or ew*eh>budget:raise ValueError('完整部件扩展参考超过当前尺寸上限，未生成或裁切')
 side=max(ew,eh)
 # Preserve rectangular native references when a square would exceed budget.
 rw,rh=(side,side) if (not allow_outside or settings().get('provider')=='aimake') and side*side<=budget else (ew,eh)
 px=(rw-ew)//2;py=(rh-eh)//2
 canvas=Image.new('RGBA',(rw,rh));canvas.paste(original,(px+mx,py+my));reference=assets/(layer['id']+'_扩展参考.png');canvas.save(reference)
 target=assets/(layer['id']+'_完整扩展.png')
 prompt=COLOR_PRESERVATION+'只提取并补全以下指定部件，其他实体和背景全部透明。'+layer['extractionBrief']+'。第一张是扩展参考画布，原图位于x='+str(px+mx)+',y='+str(py+my)+'，尺寸'+str(w)+'×'+str(h)+'。保持原对象在画布上的原位置、原大小、朝向和材质；不居中重排、不压缩塞进原框。只补缺失和遮挡，可延伸超出旧图片边界至新增透明区。完整形体不得贴边裁断。优先输出与参考'+str(rw)+'×'+str(rh)+'同宽高比、同构图的RGBA透明PNG；保持完整对象，不为适配画幅拉伸、裁断或重排。'
 if settings().get('provider')=='aimake':
  prompt+='补全验收要求：原图边缘不是物体边缘。沿可见结构连续补出被截断的车轮、牛角、管道、火焰及其他主体外缘；火焰须有自然收束的完整尖端，不可沿原图上边缘平切。新增留白就是补全区域，不要把白底参考重新裁成旧横幅。完整主体与输出四边保持可见留白；若需要更多空间，保持主体比例并扩展画幅，禁止缩小原主体或裁断。'
 images=[reference]
 # The source box describes visible evidence, never the completed alpha extent.
 if all(k in layer for k in ('x','y','width','height')):
  import json
  from PIL import ImageDraw
  x,y,bw,bh=(float(layer[k]) for k in ('x','y','width','height'))
  marked=assets/(layer['id']+'_目标标注.png')
  aligned=canvas.copy();draw=ImageDraw.Draw(aligned)
  draw.rectangle((x+px+mx,y+py+my,x+bw+px+mx,y+bh+py+my),outline='#ffdf24',width=3)
  aligned.save(marked);images.append(marked)
  context=max(24,max(bw,bh)*.6)
  bounds=(max(0,math.floor(x-context)),max(0,math.floor(y-context)),min(w,math.ceil(x+bw+context)),min(h,math.ceil(y+bh+context)))
  if bounds[2]>bounds[0] and bounds[3]>bounds[1]:
   crop=assets/(layer['id']+'_目标干净局部.png');original.crop(bounds).save(crop);images.append(crop)
  prompt+='第二张仅用黄色矩形指出本次唯一目标，第三张（如有）为未经标注和调色的原图局部上下文，不是输出构图。目标原图可见参考框xywh='+json.dumps([x,y,bw,bh])+'；在第一/二张扩展画布中的可见框xywh='+json.dumps([x+px+mx,y+py+my,bw,bh])+'。此框只定位原图已经可见的部分，不约束补全后整体边界；补全部分可越框，禁止把完整外形缩入此框。只提取本次目标，不提取邻近实体，不生成黄色框。局部图不得取代第一张的落位坐标。'
 record=CLIENT.generate(prompt,images,target,transparent=True,cancelled=cancelled,on_status=on_status,allow_identity_change=False)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('扩展素材未完成实际生成')
 registered=register_asset(target,(rw,rh),(-mx-px,-my-py))
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

 src=registered['src']
 return {'id':layer['id'],'name':layer['name'],'type':'image',**registered,'provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','assetKind':'complete-asset','assetReviewStatus':'NEEDS_REVIEW' if registered['reviewIssue'] else 'NOT_REVIEWED','review':True,'generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'generatedAssetSHA256':hashlib.sha256(base64.b64decode(src.split(',',1)[1])).hexdigest(),'expandedCanvas':True,**{k:record[k] for k in ('provider','model','genId','postprocessing') if k in record}}}
