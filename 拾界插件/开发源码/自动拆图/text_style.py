"""Fit ordinary editable text to observed glyphs, including weight and italic."""
from pathlib import Path
import base64,json,shutil,subprocess
import numpy as np
import cv2
FONTS=[('Microsoft YaHei',700,'msyhbd.ttc'),('Microsoft YaHei',400,'msyh.ttc'),('SimHei',400,'simhei.ttf'),('Arial',700,'arialbd.ttf'),('Arial',400,'arial.ttf'),('Impact',400,'impact.ttf'),('Arial Narrow',400,'arialn.ttf'),('Arial Narrow',700,'arialnb.ttf'),('Haettenschweiler',400,'HATTEN.TTF')]

def estimate(patch,text):
 h,w=patch.shape[:2]
 if min(h,w)<4 or not text:return None
 pixels=patch.reshape(-1,3);buckets=(pixels//16)*16;keys,counts=np.unique(buckets,axis=0,return_counts=True)
 key=keys[np.argmax(counts)]
 # A tightly cropped heavy heading can contain more black ink than paper.
 # Its border anchors the material polarity instead of inverting letters/holes.
 border=np.concatenate((patch[0],patch[-1],patch[:,0],patch[:,-1]))
 border_keys,border_counts=np.unique((border//16)*16,axis=0,return_counts=True)
 border_key=border_keys[np.argmax(border_counts)]
 if np.max(border_counts)/len(border)>=.35:key=border_key
 # A smooth or compressed material can straddle several 16-level buckets.
 # Treat nearby background colours as one material before applying the area
 # gate; a single exact bucket rejected real small text before glyph fitting.
 material=np.linalg.norm(pixels.astype(float)-(key.astype(float)+8),axis=1)<28
 if np.mean(material)<.2:return None
 background=np.median(pixels[material],axis=0)
 distance=np.linalg.norm(patch.astype(float)-background,axis=2)
 threshold,_=cv2.threshold(np.clip(distance,0,255).astype('uint8'),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
 observed=distance>max(30,threshold*.7);ys,xs=np.where(observed)
 if len(xs)<20:return None
 x0,y0,x1,y1=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
 target=observed[y0:y1,x0:x1];th,tw=target.shape
 edges=cv2.Canny(observed.astype('uint8')*255,50,150)
 lines=cv2.HoughLinesP(edges,1,np.pi/720,threshold=5,minLineLength=max(5,round(th*.1)),maxLineGap=4)
 slopes=[]
 if lines is not None:
  for lx,ly,rx,ry in lines[:,0]:
   if abs(ry-ly)>=max(8,round(th*.15)) and abs((rx-lx)/(ry-ly))<.45:slopes.append(float((rx-lx)/(ry-ly)))
 skew=max(0,-float(np.median(slopes))) if len(slopes)>=5 else 0
 if skew<.06 or (slopes and np.mean(np.array(slopes)<-.04)<.65):skew=0
 # Compare actual native glyphs at a uniform font size. Fitting every candidate
 # to the target width would make a broad fallback font impersonate condensed ink.
 lines=text.replace('\r\n','\n').replace('\r','\n').split('\n');line_height=None
 if len(lines)>1:
  active=np.any(target,axis=1);edges=np.diff(np.pad(active.astype(np.int8),(1,1)))
  starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
  if len(starts)==len(lines):line_height=float(np.median(np.diff(starts)))
  else:line_height=float(th/max(1,len(lines)-.2))
 node=shutil.which('node')
 if not node:raise RuntimeError('字体拟合需要与PSD相同的Node Canvas运行时')
 cjk=any('\u4e00'<=c<='\u9fff' for c in text)
 fonts=[{'family':family,'weight':weight,'file':str(Path('C:/Windows/Fonts')/file)} for family,weight,file in FONTS if (not cjk or family in ('Microsoft YaHei','SimHei')) and (Path('C:/Windows/Fonts')/file).is_file()]
 request={'text':text,'width':tw,'height':th,'mask':base64.b64encode(target.astype('uint8').tobytes()).decode(),'skew':skew,'skews':[skew] if skew else [0,.22],'fonts':fonts,'lineHeight':line_height,'uniformScale':True}
 native=subprocess.run([node,str(Path(__file__).with_name('text_candidates.cjs'))],input=json.dumps(request,ensure_ascii=False),capture_output=True,text=True,encoding='utf8',cwd=Path(__file__).resolve().parents[2],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if native.returncode:raise RuntimeError('真实导出字体拟合失败：'+native.stderr[-300:])
 fitted=json.loads(native.stdout)
 # A measured source slant remains useful when only an approximate local face
 # exists. Keep that approximation explicit rather than stretching its width.
 if fitted.get('styleMatch',0)>(.25 if skew else .35) and fitted.get('nativeDensityError',1)<.65:
  fill=np.median(patch[observed],axis=0);slope=float(fitted.get('textSkew',skew))
  result={k:fitted[k] for k in ('fontFamily','fontWeight','fontSize','styleMatch','nativeDensityError','nativeAspectError')}
  result.update(fontStyle='italic' if slope else 'normal',textSkew=slope,fitWidth=False,fill='#'+''.join(f'{int(c):02x}' for c in fill),strokeWidth=0,offsetX=x0+fitted.get('baselineOffsetX',0),offsetY=y0,glyphWidth=tw,glyphHeight=th)
  result['fontMatchApproximate']=fitted['styleMatch']<.7 or fitted.get('nativeAspectError',0)>.08 or fitted['nativeDensityError']>.15
  if line_height is not None:result['lineHeight']=line_height
  return result
 return None
