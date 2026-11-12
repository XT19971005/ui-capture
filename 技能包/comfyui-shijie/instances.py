"""Explicit, deterministic reuse of reviewed RGBA assets; no image generation."""
import math
import cv2
import numpy as np

def duplicate_layers(sources,source_names,instances):
 if not sources or len(source_names)!=len(sources):raise ValueError('源素材与名称数不一致')
 if not isinstance(instances,list) or len(instances)>200:raise ValueError('实例清单须为不超过200项的列表')
 h,w=sources[0].shape[:2]
 if (len(sources)+len(instances))*h*w>64_000_000:raise ValueError('实例总画布像素超出安全预算，请分批处理')
 for src in sources:
  if src.shape!=(h,w,4) or src.dtype!=np.uint8:raise ValueError('源素材必须为同画布RGBA uint8')
 # Validate every item before allocating output; never partly apply a bad plan.
 jobs=[];names=list(source_names)
 for row in instances:
  if not isinstance(row,dict) or row.get('source_review')!='PASS':raise ValueError('只能复用已经实际验收的源素材')
  index=row.get('source_index');name=row.get('name')
  if type(index) is not int or not 0<=index<len(sources):raise ValueError('实例源索引无效，索引从0开始')
  if not isinstance(name,str) or not name.strip() or any(ord(c)<32 or c in '\x85\u2028\u2029' for c in name):raise ValueError('实例名称须非空且无控制字符或行分隔符')
  name=name.strip()
  if name in names:raise ValueError('实例名称不能与已有层名重复')
  if any(key in row for key in ('scale_x','scale_y','color','rotate')):raise ValueError('此复用节点只支持平移与等比缩放，变体须另备底稿')
  x,y,scale=row.get('x'),row.get('y'),row.get('scale',1)
  if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x,y,scale)):raise ValueError('实例位置与比例须为有限数值')
  if int(x)!=x or int(y)!=y or not .1<=scale<=8:raise ValueError('实例坐标须为整像素，等比缩放范围0.1至8')
  yy,xx=np.nonzero(sources[index][...,3]>0)
  if not len(xx):raise ValueError('透明空素材不能作为可见实例底稿')
  box=(int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1))
  ww=max(1,round((box[2]-box[0])*scale));hh=max(1,round((box[3]-box[1])*scale))
  if x<0 or y<0 or x+ww>w or y+hh>h:raise ValueError('实例超出画布，禁止静默裁断')
  jobs.append((index,name,int(x),int(y),box,ww,hh));names.append(name)
 output=[src.copy() for src in sources];mapping=[]
 for index,name,x,y,(left,top,right,bottom),ww,hh in jobs:
  crop=sources[index][top:bottom,left:right].copy()
  if crop.shape[:2]!=(hh,ww):
   # Resize premultiplied colours so transparent pixels cannot create dark halos.
   values=crop.astype(np.float32)/255;alpha=values[...,3:4]
   premul=np.concatenate([values[...,:3]*alpha,alpha],axis=2)
   shrinking=ww<crop.shape[1] or hh<crop.shape[0]
   resized=cv2.resize(premul,(ww,hh),interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
   a=np.clip(resized[...,3:4],0,1)
   rgb=np.divide(resized[...,:3],a,out=np.zeros_like(resized[...,:3]),where=a>1e-6)
   crop=np.rint(np.clip(np.concatenate([rgb,a],axis=2),0,1)*255).astype(np.uint8)
  if not np.any(crop[...,3]>0):raise ValueError('此缩放比例使素材完全消失，请提高比例')
  canvas=np.zeros((h,w,4),np.uint8);canvas[y:y+hh,x:x+ww]=crop;output.append(canvas)
  mapping.append({'source_index':index,'instance_name':name,'target_box':[x,y,x+ww,y+hh],'source_review':'PASS','instance_review':'REQUIRED'})
 return output,names,{'source_assets':len(sources),'copied_instances':len(jobs),'generated_assets':0,'instances':mapping,'visual_review':'REQUIRED'}
