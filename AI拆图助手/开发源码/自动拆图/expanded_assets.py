"""Complete semantic assets on an expanded, registered canvas; never fit into an old box."""
import math,hashlib,base64
from pathlib import Path
from PIL import Image

def extract(source,layer,assets,cancelled,on_status):
 from image_provider import CLIENT
 from reference_fidelity import COLOR_PRESERVATION
 from engine import png
 with Image.open(source) as raw:original=raw.convert('RGBA')
 w,h=original.size
 from expansion_geometry import margins
 mx,my=margins(w,h);ew,eh=w+2*mx,h+2*my
 if max(ew,eh)>6000 or ew*eh>6000000:raise ValueError('完整部件的扩展画布超过当前尺寸上限，未生成或裁切')
 side=max(ew,eh);px=(side-ew)//2;py=(side-eh)//2
 canvas=Image.new('RGBA',(side,side));canvas.paste(original,(px+mx,py+my));reference=assets/(layer['id']+'_扩展参考.png');canvas.save(reference)
 target=assets/(layer['id']+'_完整扩展.png')
 prompt=COLOR_PRESERVATION+'只提取并补全以下指定部件，其他实体和背景全部透明。'+layer['extractionBrief']+'。第一张是扩展参考画布，原图位于x='+str(px+mx)+',y='+str(py+my)+'，尺寸'+str(w)+'×'+str(h)+'。保持原对象在画布上的原位置、原大小、朝向和材质；不居中重排、不压缩塞进原框。只补缺失和遮挡，可延伸超出旧图片边界至新增透明区。完整形体不得贴边裁断。输出与参考同构图的正方形RGBA透明PNG。'
 images=[reference]
 guide=assets.parent/'02_结构/用户原画标注.png';info=assets.parent/'02_结构/用户原画标注.json'
 if guide.is_file() and info.is_file():
  from source_annotations import RULES
  marked=assets/(layer['id']+'_扩展标注.png')
  with Image.open(guide) as im:
   aligned=Image.new('RGBA',(side,side));aligned.paste(im.convert('RGBA'),(px+mx,py+my));aligned.save(marked)
  images.append(marked);prompt+='第二张是同画布彩笔语义标注，'+RULES+'颜色说明：'+info.read_text('utf8')
 record=CLIENT.generate(prompt,images,target,transparent=True,cancelled=cancelled,on_status=on_status,allow_identity_change=False)
 if cancelled():raise InterruptedError('已取消')
 if not isinstance(record,dict) or not record.get('actualImageGeneration'):raise ValueError('扩展素材未完成实际生成')
 with Image.open(target) as im:
  if im.mode!='RGBA' or im.getchannel('A').getextrema()[0]!=0:raise ValueError('扩展素材没有真实透明通道')
  if abs(im.width/im.height-1)>.001:raise ValueError('扩展素材画幅不符，未拉伸或裁切')
  full=im.resize((side,side),Image.Resampling.LANCZOS) if im.size!=(side,side) else im.copy()
  candidate=full.crop((px,py,px+ew,py+eh));box=candidate.getchannel('A').getbbox()
  if not box or box[0]<=0 or box[1]<=0 or box[2]>=ew or box[3]>=eh:raise ValueError('扩展后主体仍可能出画，未应用；请扩大目标范围后再明确生成')
  # Never throw away generated content in the aspect-ratio padding.
  alpha=full.getchannel('A');alpha.paste(0,(px,py,px+ew,py+eh))
  if alpha.getbbox():raise ValueError('生成内容超出注册扩展范围，未裁切或应用')
 candidate.save(target);src=png(candidate)
 return {'id':layer['id'],'name':layer['name'],'type':'image','src':src,'x':-mx,'y':-my,'width':ew,'height':eh,'provenance':'aimake-image-generation' if record.get('provider')=='aimake' else 'codex-image-generation','assetKind':'complete-asset','assetReviewStatus':'NOT_REVIEWED','review':True,'generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'generatedAssetSHA256':hashlib.sha256(base64.b64decode(src.split(',',1)[1])).hexdigest(),'expandedCanvas':True,**{k:record[k] for k in ('provider','model','genId') if k in record}}}
