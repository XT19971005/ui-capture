"""Execute a bound QP plan using the server's existing ComfyUI registry."""
import inspect,math
import cv2
import numpy as np
try:
 from .auto_expert import check_bound_plan
 from .core import vector_candidate
 from .branches import prepare_text
except ImportError:
 from auto_expert import check_bound_plan
 from core import vector_candidate
 from branches import prepare_text

def invoke(registry,name,**kwargs):
 cls=registry.get(name)
 if cls is None:raise RuntimeError('服务器缺少已要求的内置节点：'+name)
 obj=cls();method=getattr(obj,getattr(cls,'FUNCTION','execute'))
 value=method(**kwargs)
 if inspect.isawaitable(value):raise RuntimeError('不支持异步内置节点调用：'+name)
 if isinstance(value,dict):value=value.get('result')
 if value is None:raise RuntimeError('内置节点无输出：'+name)
 if hasattr(value,'result'):value=value.result
 try:return tuple(value)
 except TypeError as e:raise RuntimeError('内置节点输出无效：'+name) from e

def colour_mask(rgb,row,exclusion=None):
 h,w=rgb.shape[:2];x,y,r,b=row['box'];crop=rgb[y:b,x:r].astype(float)
 colour=row.get('color')
 if colour is None:
  brightness=np.min(crop,axis=2) if row['kind']=='flat_shape' else np.max(crop,axis=2)
  colour=np.median(crop[brightness>=np.percentile(brightness,97)],axis=0)
 colour=np.asarray(colour,float);dist=np.max(abs(crop-colour),axis=2)
 alpha=np.clip(1-dist/85,0,1)
 mask=np.zeros((h,w),np.uint8);mask[y:b,x:r]=np.rint(alpha*255).astype(np.uint8)
 if exclusion is not None:mask=np.rint(mask.astype(float)*(1-exclusion)).astype(np.uint8)
 return mask,colour

def require_visible_asset(rgba,name):
 # Low-opacity shadows/glows are valid. Only a completely empty alpha is rejected.
 if not np.any(rgba[...,3]):raise ValueError('提取结果为空素材，拒绝漏项导出：'+name)

def flat_asset(rgb,row,exclusion=None):
 mask,colour=colour_mask(rgb,row,exclusion)
 rgba=np.dstack([rgb.copy(),mask]);core=cv2.erode((mask>210).astype(np.uint8),np.ones((3,3),np.uint8))>0
 samples=rgb[core].astype(float)
 flat=bool(len(samples)>=16 and np.max(abs(samples-np.median(samples,axis=0)))<=12)
 if flat:
  # Detect coherent colour ramps before replacing noisy source colour by its median.
  yy,xx=np.nonzero(core);coords=np.column_stack([xx-xx.mean(),yy-yy.mean(),np.ones(len(xx))]);fit=coords@np.linalg.lstsq(coords,samples,rcond=None)[0]
  variance=np.sum((samples-samples.mean(axis=0))**2)
  if variance>0 and 1-np.sum((samples-fit)**2)/variance>.7 and np.max(np.ptp(fit,axis=0))>3:flat=False
 if flat:
  uniform=np.dstack([np.broadcast_to(np.median(samples,axis=0).astype(np.uint8),rgb.shape).copy(),(mask>=128).astype(np.uint8)*255])
  shape=vector_candidate(uniform)
  if shape:
   return {'kind':'shape','name':row['name']+('_可见部分待补全' if row.get('occluded') else ''),'rgba':uniform,'shapes':shape['shapes'],'color':shape['color']}
 return {'kind':'bitmap','name':row['name']+'_位图待校对','rgba':rgba}

def generated_background(registry,width,height,prompt,models=None):
 # All identifiers are a fixed whitelist, never supplied as executable model names by a VLM.
 if models is None:
  unet=invoke(registry,'UNETLoader',unet_name='flux-2-klein-4b.safetensors',weight_dtype='default')[0]
  clip=invoke(registry,'CLIPLoader',clip_name='qwen_3_4b.safetensors',type='flux2',device='default')[0]
  vae=invoke(registry,'VAELoader',vae_name='flux2-vae.safetensors')[0]
 else:unet,clip,vae=models
 pos=invoke(registry,'CLIPTextEncode',clip=clip,text=prompt+' Empty backdrop only, no people, no lettering, no logos, no signs or objects.')[0]
 neg=invoke(registry,'CLIPTextEncode',clip=clip,text='')[0]
 scale=math.sqrt(1024*1024/(width*height));ww=max(16,round(width*scale/16)*16);hh=max(16,round(height*scale/16)*16)
 sigmas=invoke(registry,'Flux2Scheduler',steps=4,width=ww,height=hh)[0]
 latent=invoke(registry,'EmptyFlux2LatentImage',width=ww,height=hh,batch_size=1)[0]
 noise=invoke(registry,'RandomNoise',noise_seed=123456789)[0]
 sampler=invoke(registry,'KSamplerSelect',sampler_name='euler')[0]
 guider=invoke(registry,'CFGGuider',model=unet,positive=pos,negative=neg,cfg=1.0)[0]
 latent=invoke(registry,'SamplerCustomAdvanced',noise=noise,guider=guider,sampler=sampler,sigmas=sigmas,latent_image=latent)[0]
 image=invoke(registry,'VAEDecode',samples=latent,vae=vae)[0]
 image=invoke(registry,'ImageScale',image=image,upscale_method='lanczos',width=width,height=height,crop='disabled')[0]
 return np.rint(image[0].detach().cpu().numpy()[...,:3]*255).clip(0,255).astype(np.uint8)

def execute_plan(rgb,plan,registry,font_paths,background_mode='Klein近似重建',removal_model=None,background_models=None):
 import torch
 check_bound_plan(plan,rgb);h,w=rgb.shape[:2]
 if plan.get('pipeline')=='components-v1':
  try:from .components import execute_components
  except ImportError:from components import execute_components
  return execute_components(rgb,plan,registry,font_paths,removal_model,background_models)
 if plan.get('pipeline')!='precision-v1' and w*h*min(64,len(plan['assets'])*2+1)>64000000:raise ValueError('当前素材数量超过64百万图层像素预算，需拆批')
 if plan.get('pipeline')=='precision-v1':
  try:from .precision_pipeline import execute_precision
  except ImportError:from precision_pipeline import execute_precision
  return execute_precision(rgb,plan,registry,removal_model)
 if w*h*min(64,len(plan['assets'])+1)>64000000:raise ValueError('当前素材数量超过64百万图层像素预算，需拆批')
 assets=[];person_assets=[];warnings=list(plan.get('warnings',[]));exclusion=np.zeros((h,w),float)
 removal=np.zeros((h,w),np.uint8)
 # The person's mask also excludes clothing/skin from logos behind it.
 people=[r for r in plan['assets'] if r['kind']=='person']
 model=removal_model
 if model is None and any(r['kind'] in {'person','image'} for r in plan['assets']):
  loader=registry.get('LoadBackgroundRemovalModel')
  if loader is None:raise RuntimeError('服务器缺少BiRefNet加载节点')
  schema=loader.INPUT_TYPES()['required'];key=next((k for k,v in schema.items() if isinstance(v[0],list) and 'birefnet.safetensors' in v[0]),None)
  if key is None:raise RuntimeError('服务器BiRefNet模型不在加载清单')
  model=invoke(registry,'LoadBackgroundRemovalModel',**{key:'birefnet.safetensors'})[0]
 for row in people+[r for r in plan['assets'] if r['kind'] not in {'person','text'}]:
  kind=row['kind'];x,y,r,b=row['box']
  if kind in {'person','image'}:
   crop=np.ascontiguousarray(rgb[y:b,x:r]);tensor=torch.from_numpy(crop.astype(np.float32)/255).unsqueeze(0)
   value=invoke(registry,'RemoveBackground',bg_removal_model=model,image=tensor)[0]
   local=value.detach().cpu().numpy().squeeze()
   if local.shape!=(b-y,r-x):raise ValueError('BiRefNet返回尺寸不匹配，拒绝拉伸')
   mask=np.zeros((h,w),float);mask[y:b,x:r]=np.clip(local,0,1)
   if np.count_nonzero(mask>.1)<16:raise ValueError('未得到有效完整前景：'+row['name'])
   rgba=np.dstack([rgb.copy(),np.rint(mask*255).astype(np.uint8)])
   target=person_assets if kind=='person' else assets
   target.append({'kind':'bitmap','name':row['name'],'rgba':rgba})
   if kind=='person':exclusion=np.maximum(exclusion,mask)
  elif kind=='flat_shape':
   asset=flat_asset(rgb,row,exclusion);rgba=asset['rgba'];assets.append(asset)
   if asset['kind']!='shape':warnings.append(row['name']+'：源色变化/细笔画不满足纯色条件，保留位图')
  else:
   mask,colour=colour_mask(rgb,row,exclusion)
   rgba=np.dstack([rgb.copy(),mask]);assets.append({'kind':'bitmap','name':row['name']+'_含光晕位图','rgba':rgba})
  require_visible_asset(rgba,row['name']);removal=np.maximum(removal,rgba[...,3])
  if row.get('occluded'):warnings.append(row['name']+'：遮挡或出画，当前仅可见部分，不算完整素材')
 for row in plan['assets']:
  if row['kind']!='text':continue
  item={'text':row['text'],'box':row['box'],'render_as':'text'}
  if row.get('color') is not None:item['color']=row['color']
  try:
   _,branch=prepare_text(rgb,{'texts':[item]},font_paths)
   for a in branch['assets']:
    # Native text must keep a truthful full cache. Put the foreground person above
    # it in the actual PSD, so editing/re-rendering does not reveal hidden strokes.
    if a['kind']!='text':a['rgba'][...,3]=np.rint(a['rgba'][...,3].astype(float)*(1-exclusion)).astype(np.uint8)
    require_visible_asset(a['rgba'],row['name'])
    assets.append(a);removal=np.maximum(removal,a['rgba'][...,3])
   warnings.extend(branch['warnings'])
  except ValueError as error:
   mask,_=colour_mask(rgb,dict(row,color=row.get('color')),exclusion)
   rgba=np.dstack([rgb.copy(),mask]);require_visible_asset(rgba,row['name']);assets.append({'kind':'bitmap','name':row['name']+'_文字待校对','rgba':rgba});removal=np.maximum(removal,mask)
   warnings.append(row['name']+'：'+str(error))
 if background_mode=='Klein近似重建':background=generated_background(registry,w,h,plan['background_prompt'],background_models)
 else:background=cv2.inpaint(rgb.copy(),cv2.dilate((removal>10).astype(np.uint8)*255,np.ones((7,7),np.uint8)),5,cv2.INPAINT_TELEA)
 assets.extend(person_assets)
 warnings.append('人物置于标识/文字前以保持真实遮挡；背景为近似重建；所有素材及原生字形/轮廓均须实际视觉验收')
 return np.dstack([background,np.full((h,w),255,np.uint8)]),assets,warnings
