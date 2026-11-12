"""Independent text/vector/image asset branches, in source canvas coordinates."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
try:
 from .core import validate_plan,estimate_ink,vector_candidate
 from .exporter import _text_image
except ImportError:
 from core import validate_plan,estimate_ink,vector_candidate
 from exporter import _text_image

def _ink_mask(rgb,row):
 h,w=rgb.shape[:2];x,y,r,b=map(int,row['box']);colour=np.array(row.get('color',estimate_ink(rgb,row['box'])),float)
 crop=rgb[y:b,x:r,:3].astype(float)
 # Select foreground by ink distance, then include only adjacent antialias pixels.
 distance=np.max(abs(crop-colour),axis=2);core=(distance<55).astype('uint8')
 fringe=cv2.dilate(core,np.ones((3,3),np.uint8))>0
 background=np.median(crop[distance>=np.percentile(distance,85)],axis=0)
 bg_distance=np.max(abs(crop-background),axis=2)
 local=fringe & (distance<110) & (distance<bg_distance)
 mask=np.zeros((h,w),np.uint8);mask[y:b,x:r]=local.astype('uint8')*255
 points=cv2.findNonZero(mask)
 if points is None:raise ValueError('文字/矢量区未提取到明确前景：'+row.get('text',row.get('name','未命名')))
 a,c,ww,hh=cv2.boundingRect(points)
 return mask,[a,c,a+ww,c+hh],colour.astype(int).tolist()

def _removal_mask(mask):
 return cv2.dilate((mask>0).astype('uint8'),np.ones((3,3),np.uint8))*255

def _remove(rgb,mask):
 # Inpaint on full canvas, not a tight OCR crop: outside context prevents border ghosts.
 removal=_removal_mask(mask)
 return cv2.inpaint(np.asarray(rgb)[...,:3].copy(),removal,4,cv2.INPAINT_TELEA)

def _fit_font(text,target,paths):
 best=None;h,w=target.shape
 for path in paths:
  for size in range(max(8,h-3),max(9,h*2)+1):
   try:
    f=ImageFont.truetype(str(path),size);box=f.getbbox(text,anchor='ls');ww=max(1,box[2]-box[0]);hh=max(1,box[3]-box[1])
    glyph=Image.new('L',(ww,hh));ImageDraw.Draw(glyph).text((-box[0],-box[1]),text,font=f,anchor='ls',fill=255)
    scale=min(w/ww,h/hh)
    fitted=glyph.resize((max(1,round(ww*scale)),max(1,round(hh*scale))),Image.Resampling.LANCZOS)
    trial_image=Image.new('L',(w,h));trial_image.paste(fitted,(0,0))
    trial=np.asarray(trial_image)>100
    union=np.count_nonzero(trial|target);score=np.count_nonzero(trial&target)/max(1,union)
    if best is None or score>best[0]:best=(score,Path(path),size)
   except (OSError,ValueError):continue
 if best is None:raise ValueError('文字分支没有可用字体')
 return best

def prepare_text(rgb,plan,font_paths,allow_approximate=False):
 rgb=np.asarray(rgb,dtype='uint8')[...,:3];h,w=rgb.shape[:2];validate_plan(plan,w,h)
 clean=rgb.copy();assets=[];diagnostics=[];warnings=[]
 for row in plan.get('texts',[]):
  mask,box,colour=_ink_mask(rgb,row);clean=_remove(clean,mask)
  if row.get('render_as')=='vector':continue
  x,y,r,b=box;score,font,render_size=_fit_font(row['text'],mask[y:b,x:r]>0,font_paths)
  refined=dict(row,box=box,color=colour,font_render_size=render_size);rgba,native=_text_image(refined,font,w,h)
  if score>=(.55 if allow_approximate else .65):
   assets.append({'kind':'text','name':'文字_'+row['text'],'rgba':rgba,'text':native})
  else:
   preserved=np.dstack([rgb.copy(),_removal_mask(mask)])
   assets.append({'kind':'bitmap','name':'字形待校对_'+row['text'],'rgba':preserved})
  diagnostics.append({'text':row['text'],'box':box,'font':font.name,'font_mask_iou':round(score,4),'render_size':render_size,'approximate_allowed':allow_approximate,'review':'REQUIRED'})
  if score<.65:warnings.append('字形匹配未达标，需校对：'+row['text'])
 return clean,{'width':w,'height':h,'assets':assets,'diagnostics':diagnostics,'warnings':warnings}

def prepare_vectors(original,clean,plan):
 original=np.asarray(original,dtype='uint8')[...,:3];h,w=original.shape[:2];validate_plan(plan,w,h)
 rows=[dict(t,name='艺术字_'+t['text']) for t in plan.get('texts',[]) if t.get('render_as')=='vector']+plan.get('vectors',[])
 assets=[];warnings=[];clean=np.asarray(clean,dtype='uint8')[...,:3].copy()
 for row in rows:
  validate_plan({'texts':[dict(row,text=row.get('text',row.get('name','矢量')))]},w,h)
  mask,box,colour=_ink_mask(original,row)
  rgba=np.dstack([original.copy(),mask])
  interior=cv2.erode((mask>0).astype('uint8'),np.ones((3,3),np.uint8))>0
  if row.get('render_as')=='vector':
   deep=cv2.erode((mask>0).astype('uint8'),np.ones((7,7),np.uint8))>0
   if deep.sum()>=16:interior=deep
  samples=original[interior] if interior.any() else original[mask>0]
  flat=bool(len(samples) and np.max(abs(samples.astype(float)-np.median(samples,axis=0)))<=10)
  # A small but coherent spatial colour trend is still a gradient, not JPEG noise.
  selected=interior if interior.any() else mask>0
  yy,xx=np.nonzero(selected)
  if flat and len(xx)>=16:
   coords=np.column_stack([xx-xx.mean(),yy-yy.mean(),np.ones(len(xx))])
   values=samples.astype(float);fit=coords@np.linalg.lstsq(coords,values,rcond=None)[0]
   variance=np.sum((values-values.mean(axis=0))**2)
   explained=1-np.sum((values-fit)**2)/max(variance,1e-9)
   if explained>.7 and np.max(np.ptp(fit,axis=0))>3:flat=False
  if flat:rgba[...,:3]=np.median(samples,axis=0).astype('uint8')
  shape=vector_candidate(rgba) if flat else None
  if shape and row.get('render_as')=='vector':
   try:from .bezier import mask_to_paths
   except ImportError:from bezier import mask_to_paths
   exact,_=mask_to_paths((mask>0).astype('uint8'),tolerance=.35,smooth_pixels=0,preserve_corners=True)
   if exact:shape['shapes']=exact
  if shape is None:
   rgba=np.dstack([original.copy(),_removal_mask(mask)])
   warnings.append('存在渐变/纹理或细小断片，保留原像素位图待校对：'+row.get('name','矢量候选'))
   assets.append({'kind':'bitmap','name':row.get('name','矢量候选待修'),'rgba':rgba})
  else:assets.append({'kind':'shape','name':row.get('name','纯色图形'),'rgba':rgba,'shapes':shape['shapes'],'color':shape['color']})
  clean=_remove(clean,mask)
 return clean,{'width':w,'height':h,'assets':assets,'warnings':warnings,'diagnostics':[]}

def combine_branches(images,text_branch,vector_branch,names=None):
 if not images:raise ValueError('图片分支为空')
 h,w=images[0].shape[:2]
 for branch in (text_branch,vector_branch):
  if branch.get('width')!=w or branch.get('height')!=h:raise ValueError('分支画布坐标不一致，禁止静默缩放')
  for a in branch['assets']:
   if a['rgba'].shape!=(h,w,4):raise ValueError('分支资产尺寸不一致')
 return [{'kind':'bitmap','name':names[i] if names else f'图片_{i+1:02d}','rgba':rgba} for i,rgba in enumerate(images)]+vector_branch['assets']+text_branch['assets']
