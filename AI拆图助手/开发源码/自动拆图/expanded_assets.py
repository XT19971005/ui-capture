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
 from image_provider import CLIENT
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
 budget=36000000 if allow_outside or w*h>6000000 else 6000000
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
 rw,rh=(side,side) if not allow_outside and side*side<=budget else (ew,eh)
 px=(rw-ew)//2;py=(rh-eh)//2
 canvas=Image.new('RGBA',(rw,rh));canvas.paste(original,(px+mx,py+my));reference=assets/(layer['id']+'_扩展参考.png');canvas.save(reference)
 target=assets/(layer['id']+'_完整扩展.png')
 prompt=COLOR_PRESERVATION+'只提取并补全以下指定部件，其他实体和背景全部透明。'+layer['extractionBrief']+'。第一张是扩展参考画布，原图位于x='+str(px+mx)+',y='+str(py+my)+'，尺寸'+str(w)+'×'+str(h)+'。保持原对象在画布上的原位置、原大小、朝向和材质；不居中重排、不压缩塞进原框。只补缺失和遮挡，可延伸超出旧图片边界至新增透明区。完整形体不得贴边裁断。优先输出与参考'+str(rw)+'×'+str(rh)+'同宽高比、同构图的RGBA透明PNG；保持完整对象，不为适配画幅拉伸、裁断或重排。'
 images=[reference]
 guide=assets.parent/'02_结构/用户原画标注.png';info=assets.parent/'02_结构/用户原画标注.json'
 if guide.is_file() and info.is_file():
  from source_annotations import RULES
  marked=assets/(layer['id']+'_扩展标注.png')
  from source_annotations import draw_marks
  import json
  mark_data=json.loads(info.read_text('utf8'));mark_items=mark_data['items'] if isinstance(mark_data,dict) else mark_data
  aligned=canvas.copy();draw_marks(aligned,mark_items,(px+mx,py+my));aligned.save(marked)
  images.append(marked);prompt+='第二张是同画布彩笔语义标注，'+RULES+'颜色说明：'+info.read_text('utf8')
 record=CLIENT.generate(prompt,images,target,transparent=True,cancelled=cancelled,on_status=on_status,allow_identity_change=False)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('扩展素材未完成实际生成')
 registered=register_asset(target,(rw,rh),(-mx-px,-my-py))
 from asset_registration import calibrate
 if on_status:on_status('正在自动校对素材大小与位置…')
 registered=calibrate(source,registered,layer) if all(k in layer for k in ('x','y','width','height')) else registered
 src=registered['src']
 return {'id':layer['id'],'name':layer['name'],'type':'image',**registered,'provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','assetKind':'complete-asset','assetReviewStatus':'NEEDS_REVIEW' if registered['reviewIssue'] else 'NOT_REVIEWED','review':True,'generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'generatedAssetSHA256':hashlib.sha256(base64.b64decode(src.split(',',1)[1])).hexdigest(),'expandedCanvas':True,**{k:record[k] for k in ('provider','model','genId','postprocessing') if k in record}}}
