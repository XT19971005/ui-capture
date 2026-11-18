"""Independent asset references and measured native-pixel resolution; no output resampling."""
import math,re
from pathlib import Path
from PIL import Image

REFERENCE_SIDE=1536
MIN_SUBJECT_LONG_EDGE=1024

def prepare_reference(original,box,path,allowed_ratios=None):
 keys=('x','y','width','height');present=[key in box for key in keys]
 if any(present) and not all(present):raise ValueError('独立素材参考范围须完整提供x/y/width/height，或全部省略')
 x,y,w,h=(float(box[k]) for k in keys) if all(present) else (0,0,original.width,original.height)
 if not all(math.isfinite(v) for v in (x,y,w,h)) or min(w,h)<=0:raise ValueError('独立素材参考范围无效')
 pad=max(2,max(w,h)*.08)
 left=max(0,math.floor(x-pad));top=max(0,math.floor(y-pad))
 right=min(original.width,math.ceil(x+w+pad));bottom=min(original.height,math.ceil(y+h+pad))
 if right<=left or bottom<=top:raise ValueError('独立素材范围没有原图可见参考')
 crop=original.crop((left,top,right,bottom)).convert('RGBA')
 ratio=max(1/3,min(3,crop.width/crop.height))
 ratios=allowed_ratios if allowed_ratios is not None else ['1:1','3:2','2:3','4:3','3:4','16:9','9:16','21:9','9:21','3:1','1:3']
 if ratios:
  candidates=[]
  for value in ratios:
   if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',value):continue
   a,b=map(int,value.split(':'));common=math.gcd(a,b);a//=common;b//=common
   # Common multiples preserve the model enum exactly, including 21:9.
   multiple=max(1,REFERENCE_SIDE//(max(a,b)*16),math.ceil(512/(min(a,b)*16)))
   cw,ch=a*16*multiple,b*16*multiple
   if max(cw,ch)>6000 or cw*ch>6000000:continue
   candidates.append((abs(math.log((a/b)/ratio)),cw,ch,value))
  if not candidates:raise ValueError('模型没有可安全使用的独立素材画幅比例，未生成')
  _,rw,rh,selected_ratio=min(candidates)
 else:
  # Explicit empty choices means a model supports custom width and height.
  rw,rh=(REFERENCE_SIDE,max(512,round(REFERENCE_SIDE/ratio/16)*16)) if ratio>=1 else (max(512,round(REFERENCE_SIDE*ratio/16)*16),REFERENCE_SIDE)
  selected_ratio=None
 scale=min(rw*.8/crop.width,rh*.8/crop.height)
 width=max(1,round(crop.width*scale));height=max(1,round(crop.height*scale))
 # Only the input reference is enlarged. Generated PNG bytes are never resized.
 reference=Image.new('RGBA',(rw,rh))
 offset=((rw-width)//2,(rh-height)//2)
 reference.paste(crop.resize((width,height),Image.Resampling.LANCZOS),offset)
 reference.save(path);reference.close();crop.close()
 return {'referenceSize':max(rw,rh),'referenceWidth':rw,'referenceHeight':rh,'referenceToSourceScale':1/scale,
         'sourceOrigin':(left-offset[0]/scale,top-offset[1]/scale),
         'sourceCanvasSize':(rw/scale,rh/scale),
         'sourceCrop':[left,top,right,bottom],'selectedAspectRatio':selected_ratio}


def pad_reference_minimum(source,target,minimum=300):
 """Pad only a temporary reference copy; keep native source pixels one-to-one."""
 with Image.open(source) as original:
  if min(original.size)>=minimum:return False
  rgba=original.convert('RGBA')
 canvas=Image.new('RGBA',(max(minimum,rgba.width),max(minimum,rgba.height)))
 canvas.paste(rgba,((canvas.width-rgba.width)//2,(canvas.height-rgba.height)//2))
 canvas.save(target);canvas.close();rgba.close()
 return True

def resolution_prompt(frame=None):
 size=(str(frame['referenceWidth'])+'×'+str(frame['referenceHeight'])) if frame else '按目标比例选择横、竖或方形'
 return ('本次生成高清独立素材，输出独立'+size+'画幅，主体长边至少约1024实际像素，'
         '画幅随主体比例选择横、竖或方形，完整主体占画幅主要区域，四周保留约10%至15%安全留白，不触边，不裁切；极细长素材增加透明留白，不拉伸变形。'
         '不要让小物件仍按整图比例只占几十像素。第一张是放大的目标局部主参考，'
         '后面的原图只用于识别材质、造型、朝向和遮挡关系，不是输出布局。'
         '完整补全遮挡和出画部分，保持身份、比例、颜色与材质；主体在独立画幅居中。'
         '不拉伸、不压缩、不把补全形体塞进旧可见框。'
         '原图坐标、原位置、原大小只用于程序回填，不要求在输出PNG中维持整图位置或像素大小。'
         '真正RGBA透明PNG，不绘制棋盘格、标线或其它对象。')

def inspect_resolution(file):
 with Image.open(file) as image:
  alpha=image.convert('RGBA').getchannel('A')
  visible=alpha.point(lambda value:255 if value>=16 else 0).getbbox()
  if visible is None:visible=alpha.getbbox()
  if visible is None:raise ValueError('独立素材为空透明图片')
  width,height=visible[2]-visible[0],visible[3]-visible[1]
  return {'rawWidth':image.width,'rawHeight':image.height,'subjectBounds':list(visible),
          'subjectWidth':width,'subjectHeight':height,'subjectLongEdge':max(width,height),
          'minimumSubjectLongEdge':MIN_SUBJECT_LONG_EDGE,
          'status':'MEETS_PIXEL_TARGET' if max(width,height)>=MIN_SUBJECT_LONG_EDGE else 'LOW_RESOLUTION',
          'measurement':'alpha>=16 bounds; pixel count only, not visual detail approval'}

def apply_resolution(node,file,record=None,*,reused=False):
 measured=inspect_resolution(file);measured['origin']='existing-preserved' if reused else 'new-generation'
 node['assetResolution']=measured
 if record is not None:record['assetResolution']=measured.copy()
 if measured['status']=='LOW_RESOLUTION':
  note='主体实际长边仅'+str(measured['subjectLongEdge'])+'像素，未达到约1024像素高清目标；保留原PNG，不放大冒充高清、不自动重生'
  node.update(resolutionReviewRequired=True,resolutionReviewIssue=note,review=True,assetReviewStatus='NEEDS_REVIEW')
  if note not in node.get('reviewIssue',''):node['reviewIssue']='；'.join(filter(None,[node.get('reviewIssue'),note]))
 return node
