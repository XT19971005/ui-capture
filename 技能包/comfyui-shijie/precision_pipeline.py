"""Explicit deterministic branches. Data-only plans; no external model or network calls."""
import cv2
import numpy as np
from PIL import Image,ImageDraw

def select_background(fallback,override=None):
 if override is None:return fallback
 if override.shape!=fallback.shape or override.dtype!=np.uint8:raise ValueError('独立背景必须与原图同尺寸RGBA，拒绝拉伸')
 if not np.all(override[...,3]==255):raise ValueError('独立背景含透明空洞，拒绝导出')
 return override.copy()

def ordered(rows):
 if any(type(r.get('z')) is not int for r in rows) or len({r['z'] for r in rows})!=len(rows):raise ValueError('精细方案需要唯一整数z层序')
 return sorted(rows,key=lambda r:r['z'])

def unmix(source,bg,alpha):
 alpha=np.clip(alpha,0,1);safe=np.maximum(alpha,.01)[...,None]
 foreground=(np.asarray(source,float)-np.asarray(bg,float)*(1-alpha[...,None]))/safe
 foreground[alpha<=.01]=0
 return np.dstack([np.rint(np.clip(foreground,0,255)).astype(np.uint8),np.rint(alpha*255).astype(np.uint8)])

def plane(rgb,valid):
 h,w=rgb.shape[:2];yy,xx=np.mgrid[:h,:w];x=xx/max(1,w-1);y=yy/max(1,h-1)
 design=np.stack([np.ones_like(x),x,y],axis=-1)
 keep=np.flatnonzero(valid.ravel())[::max(1,int(valid.sum())//12000)]
 if len(keep)<16:raise ValueError('可观测背景样本不足，不能恢复软Alpha')
 coef=np.linalg.lstsq(design.reshape(-1,3)[keep],rgb.reshape(-1,3)[keep],rcond=None)[0]
 return np.clip(design@coef,0,255)

def restore_background(rgb,removal):
 # The real alpha union controls removal. Rectangular ROIs only locate objects.
 hard=cv2.dilate((removal>2).astype(np.uint8),np.ones((19,19),np.uint8))
 valid=hard==0;base=plane(rgb,valid);weight=valid.astype(float)
 residual=rgb.astype(float)-base;sigma=max(12,min(rgb.shape[:2])/10)
 den=cv2.GaussianBlur(weight,(0,0),sigma)
 correction=np.zeros_like(base)
 for c in range(3):
  num=cv2.GaussianBlur(residual[...,c]*weight,(0,0),sigma)
  correction[...,c]=num/np.maximum(den,1e-6)
 candidate=np.clip(base+correction,0,255)
 # Blend through clean context outside a dilated foreground mask, never across
 # foreground pixels. This retains observed sky without hard patch boundaries.
 distance=cv2.distanceTransform((1-hard).astype(np.uint8),cv2.DIST_L2,3)
 mix=np.clip(1-distance/24,0,1);mix= mix*mix*(3-2*mix)
 return np.rint(candidate*mix[...,None]+rgb*(1-mix[...,None])).clip(0,255).astype(np.uint8)

def precise_glyph(alpha,origin,canvas_shape):
 try:from .bezier import mask_to_paths
 except ImportError:from bezier import mask_to_paths
 high=cv2.resize(np.asarray(alpha,float),None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
 binary=(high>=.5).astype(np.uint8)
 shapes,stats=mask_to_paths(binary,origin=origin,pixel_size=.25,tolerance=.18,smooth_pixels=0,minimum_area=.1,preserve_corners=True,corner_minimum=.18)
 if not shapes:raise ValueError('精细字形路径为空')
 # Supersampled coverage cache; preserve square corners instead of rounding
 # the entire contour through the generic bitmap-vector smooth fitter.
 coverage=cv2.resize(binary.astype(float), (alpha.shape[1],alpha.shape[0]),interpolation=cv2.INTER_AREA)
 h,w=canvas_shape;x,y=origin;rgba=np.zeros((h,w,4),np.uint8);rgba[...,:3]=255
 rgba[y:y+alpha.shape[0],x:x+alpha.shape[1],3]=np.rint(coverage*255).astype(np.uint8)
 return rgba,dict(shapes=shapes,color=[255,255,255],stats=stats)

def restore_panel(rgb,row):
 h,w=rgb.shape[:2];x,y,r,b=row['box'];scale=3
 mask=Image.new('L',(w*scale,h*scale));d=ImageDraw.Draw(mask)
 d.rounded_rectangle((x*scale,y*scale,(r-1)*scale,(b-1)*scale),radius=row.get('radius',12)*scale,fill=255)
 outer=np.asarray(mask.resize((w,h),Image.Resampling.LANCZOS))/255
 if row.get('source_pixels'):
  return np.dstack([rgb.copy(),np.rint(outer*255).astype(np.uint8)])
 edge=row.get('border',6);inner=Image.new('L',(w*scale,h*scale));di=ImageDraw.Draw(inner)
 di.rounded_rectangle(((x+edge)*scale,(y+edge)*scale,(r-edge-1)*scale,(b-edge-1)*scale),radius=max(1,row.get('radius',12)-edge)*scale,fill=255)
 inside=np.asarray(inner.resize((w,h),Image.Resampling.LANCZOS))/255
 fill=np.asarray(row['fill'],float);frame=np.asarray(row.get('border_color',[195,237,247]),float)
 # Controlled reconstruction, never a cutout with text-shaped holes.
 dist=cv2.distanceTransform((inside>.5).astype(np.uint8),cv2.DIST_L2,3)
 shade=(np.exp(-dist/12)*row.get('inner_shadow',.22))[...,None]
 colour=np.broadcast_to(fill,(h,w,3)).copy()*(1-shade)
 fraction=np.clip(inside/np.maximum(outer,.001),0,1)[...,None]
 colour=colour*fraction+frame*(1-fraction)
 colour[outer==0]=0
 return np.dstack([np.rint(colour).clip(0,255).astype(np.uint8),np.rint(outer*255).astype(np.uint8)])

def execute_precision(rgb,plan,registry,model):
 import torch
 try:from .auto_pipeline import invoke,require_visible_asset
 except ImportError:from auto_pipeline import invoke,require_visible_asset
 try:from .core import vector_candidate
 except ImportError:from core import vector_candidate
 try:from .spatial import compact_asset
 except ImportError:from spatial import compact_asset
 h,w=rgb.shape[:2];rows=ordered(plan['assets']);assets=[]
 for row in rows:
  box=row.get('box')
  if not isinstance(box,list) or len(box)!=4 or any(type(v) is not int for v in box):raise ValueError('精细分支需要整数像素框')
  x,y,r,b=box
  if not 0<=x<r<=w or not 0<=y<b<=h:raise ValueError('精细分支区域越界')
 warnings=list(plan.get('warnings',[]));warnings+=['精细分支：面板为参数化重建，背景为原图采样拟合，均需真实视觉验收']
 removal=np.zeros((h,w),np.uint8)
 all_excluded=np.zeros((h,w),np.uint8)
 for row in rows:
  x,y,r,b=row['box'];all_excluded[y:b,x:r]=1
 for row in rows:
  x,y,r,b=row['box'];crop=rgb[y:b,x:r];method=row['method'];entries=[]
  if method=='panel':
   entries=[dict(kind='bitmap',name=row['name'],rgba=restore_panel(rgb,row))]
  elif method=='biref':
   if model is None:raise ValueError('精细分支需显式传入已有BiRefNet模型')
   tensor=torch.from_numpy(crop.astype(np.float32)/255).unsqueeze(0)
   mask=invoke(registry,'RemoveBackground',bg_removal_model=model,image=tensor)[0].detach().cpu().numpy().squeeze()
   if mask.shape!=crop.shape[:2]:raise ValueError('BiRefNet尺寸不匹配')
   rgba=np.zeros((h,w,4),np.uint8);rgba[y:b,x:r]=np.dstack([crop,np.rint(np.clip(mask,0,1)*255).astype(np.uint8)])
   entries=[dict(kind='bitmap',name=row['name'],rgba=rgba)]
  elif method in ('yellow_matte','white_matte','glyph_effect'):
   if method=='glyph_effect':
    fill=np.asarray(row['background_color'],float);localbg=np.broadcast_to(fill,crop.shape)
    white=np.clip(np.min((crop.astype(float)-localbg)/np.maximum(1,255-localbg),axis=2),0,1)
    darkcol=np.asarray(row.get('effect_color',[15,72,89]),float)
    dark=np.clip(np.max((localbg-crop.astype(float))/np.maximum(1,localbg-darkcol),axis=2),0,1)
    dark=np.where(dark>.025,dark,0)*(1-white)
    effect=np.zeros((h,w,4),np.uint8);effect[y:b,x:r]=np.dstack([np.broadcast_to(darkcol,crop.shape).astype(np.uint8),np.rint(dark*255).astype(np.uint8)])
    entries.append(dict(kind='bitmap',name=row['name']+'_描边及投影',rgba=effect))
    core,shape=precise_glyph(white,(x,y),(h,w))
    if not shape:raise ValueError('白色字形未得到有效原生形状，不能悄悄降级')
    entries.append(dict(kind='shape',name=row['name']+'_白色原生形状',rgba=core,shapes=shape['shapes'],color=shape['color']))
   else:
    if method=='yellow_matte':
     valid=(crop[...,2].astype(float)-crop[...,0])>30
     localbg=plane(crop,valid)
     fg=np.asarray(row.get('matte_color',[245,220,0]),float)
     delta=fg-localbg;alpha=np.clip(np.sum((crop-localbg)*delta,axis=2)/np.maximum(1,np.sum(delta*delta,axis=2)),0,1)
     alpha=np.where(alpha>.012,alpha,0)
    else:
     localbg=np.broadcast_to(np.asarray(row['background_color'],float),crop.shape)
     alpha=np.clip(np.min((crop-localbg)/np.maximum(1,255-localbg),axis=2),0,1)
    rgba=np.zeros((h,w,4),np.uint8);rgba[y:b,x:r]=unmix(crop,localbg,alpha)
    entries=[dict(kind='bitmap',name=row['name'],rgba=rgba)]
  else:raise ValueError('未知精细分支方法：'+str(method))
  for a in entries:
   require_visible_asset(a['rgba'],a['name']);np.maximum(removal,a['rgba'][...,3],out=removal);assets.append(compact_asset(a))
  if row.get('occluded'):warnings.append(row['name']+'：遮挡或出画，未恢复隐藏部分')
 background=restore_background(rgb,removal)
 warnings.append('背景使用真实Alpha并集、膨胀清理与连续上下文过渡，仍需检查纹理与隐藏部分重建')
 return np.dstack([background,np.full((h,w),255,np.uint8)]),assets,warnings
