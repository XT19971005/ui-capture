"""Fit ordinary editable text to observed glyphs, including weight and italic."""
from pathlib import Path
import base64,json,shutil,subprocess
from PIL import Image, ImageFont, ImageDraw
import numpy as np
import cv2
FONTS=[('Microsoft YaHei',700,'msyhbd.ttc'),('Microsoft YaHei',400,'msyh.ttc'),('SimHei',400,'simhei.ttf'),('Arial',700,'arialbd.ttf'),('Arial',400,'arial.ttf')]

def estimate(patch,text):
 h,w=patch.shape[:2]
 if min(h,w)<4 or not text:return None
 pixels=patch.reshape(-1,3);buckets=(pixels//16)*16;keys,counts=np.unique(buckets,axis=0,return_counts=True)
 key=keys[np.argmax(counts)];material=np.all(buckets==key,axis=1)
 if np.mean(material)<.2:return None
 background=np.median(pixels[material],axis=0)
 distance=np.linalg.norm(patch.astype(float)-background,axis=2)
 threshold,_=cv2.threshold(np.clip(distance,0,255).astype('uint8'),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
 observed=distance>max(30,threshold*.7);ys,xs=np.where(observed)
 if len(xs)<20:return None
 x0,y0,x1,y1=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
 target=observed[y0:y1,x0:x1];th,tw=target.shape;best=None
 edges=cv2.Canny(observed.astype('uint8')*255,50,150)
 lines=cv2.HoughLinesP(edges,1,np.pi/720,threshold=5,minLineLength=max(5,round(th*.1)),maxLineGap=4)
 slopes=[]
 if lines is not None:
  for lx,ly,rx,ry in lines[:,0]:
   if abs(ry-ly)>=max(8,round(th*.15)) and abs((rx-lx)/(ry-ly))<.45:slopes.append(float((rx-lx)/(ry-ly)))
 skew=max(0,-float(np.median(slopes))) if len(slopes)>=5 else 0
 if skew<.06 or (slopes and np.mean(np.array(slopes)<-.04)<.65):skew=0
 candidate_slopes=(skew,) if skew else (0,.22)
 for family,weight,file in FONTS:
  if family=='Arial' and any('\u4e00'<=c<='\u9fff' for c in text):continue
  path=Path('C:/Windows/Fonts')/file
  if not path.is_file():continue
  reference=ImageFont.truetype(str(path),100).getbbox(text);size=max(6,round(th*100/max(1,reference[3]-reference[1])))
  font=ImageFont.truetype(str(path),size);bounds=font.getbbox(text)
  glyph=Image.new('L',(bounds[2]-bounds[0]+12,bounds[3]-bounds[1]+8))
  ImageDraw.Draw(glyph).text((6-bounds[0],4-bounds[1]),text,font=font,fill=255)
  for slope in candidate_slopes:
   transformed=glyph
   if slope:
    gh=glyph.height;transformed=glyph.transform((glyph.width+int(gh*slope)+2,gh),Image.Transform.AFFINE,(1,slope,-slope*gh,0,1,0),resample=Image.Resampling.BICUBIC)
   box=transformed.getbbox()
   if not box:continue
   fitted=np.array(transformed.crop(box).resize((tw,th),Image.Resampling.LANCZOS))>128
   union=np.count_nonzero(target|fitted);score=np.count_nonzero(target&fitted)/max(1,union)
   if best is None or score>best[0]:
    fill=np.median(patch[observed],axis=0)
    best=(score,{'fontFamily':family,'fontWeight':weight,'fontStyle':'italic' if slope else 'normal','textSkew':float(slope),'fontSize':size,'fitWidth':True,'fill':'#'+''.join(f'{int(c):02x}' for c in fill),'strokeWidth':0,'offsetX':x0,'offsetY':y0,'glyphWidth':tw,'glyphHeight':th,'styleMatch':round(float(score),4)})
 if best and best[0]>.35:
  result=best[1];node=shutil.which('node')
  if not node:raise RuntimeError('字体拟合需要与PSD相同的Node Canvas运行时')
  request={'text':text,'width':tw,'height':th,'mask':base64.b64encode(target.astype('uint8').tobytes()).decode(),'skew':result['textSkew']}
  native=subprocess.run([node,str(Path(__file__).with_name('text_candidates.cjs'))],input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,encoding='utf8',cwd=Path(__file__).resolve().parents[2],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if native.returncode:raise RuntimeError('真实导出字体拟合失败：'+native.stderr[-300:])
  fitted=json.loads(native.stdout);result.update({k:fitted[k] for k in ('fontFamily','fontWeight','fontSize','styleMatch','nativeDensityError')})
  return result
 return None
