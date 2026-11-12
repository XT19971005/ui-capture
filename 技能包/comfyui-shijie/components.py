"""Explicit component branches in ComfyUI. Plans are data, never executable code."""
import numpy as np,cv2
from PIL import Image,ImageDraw

def component_mask(w,h,row):
 x,y,r,b=row["box"];im=Image.new("L",(w*3,h*3));d=ImageDraw.Draw(im)
 def points(poly):return [(int(a*3),int(c*3)) for a,c in poly]
 if row.get("polygon"):d.polygon(points(row["polygon"]),fill=255)
 elif row.get("ellipse"):d.ellipse((x*3,y*3,(r-1)*3,(b-1)*3),fill=255)
 else:d.rounded_rectangle((x*3,y*3,(r-1)*3,(b-1)*3),radius=row.get("radius",0)*3,fill=255)
 for hole in row.get("holes",[]):d.polygon(points(hole),fill=0)
 return np.asarray(im.resize((w,h),Image.Resampling.LANCZOS))

def clean_surface(rgb,boxes):
 mask=np.zeros(rgb.shape[:2],np.uint8)
 for x,y,r,b in boxes:mask[y:b,x:r]=255
 if not np.any(mask):return rgb.copy()
 return cv2.inpaint(rgb,mask,5,cv2.INPAINT_TELEA)

def repair_background(rgb,boxes):return clean_surface(rgb,boxes)

def edit_container(crop,prompt,registry,models):
 import torch,math
 try:from .auto_pipeline import invoke
 except ImportError:from auto_pipeline import invoke
 if models is None:raise ValueError("Container editing requires explicitly connected open source models")
 unet,clip,vae=models;h,w=crop.shape[:2];scale=min(1,(768*768/(w*h))**.5);ww=max(16,round(w*scale/16)*16);hh=max(16,round(h*scale/16)*16)
 ref=cv2.resize(crop,(ww,hh),interpolation=cv2.INTER_AREA);tensor=torch.from_numpy(ref.astype(np.float32)/255).unsqueeze(0)
 pos=invoke(registry,"CLIPTextEncode",clip=clip,text=prompt)[0];neg=invoke(registry,"CLIPTextEncode",clip=clip,text="")[0]
 encoded=invoke(registry,"VAEEncode",pixels=tensor,vae=vae)[0]
 pos=invoke(registry,"ReferenceLatent",conditioning=pos,latent=encoded)[0];neg=invoke(registry,"ReferenceLatent",conditioning=neg,latent=encoded)[0]
 sigmas=invoke(registry,"Flux2Scheduler",steps=4,width=ww,height=hh)[0];latent=invoke(registry,"EmptyFlux2LatentImage",width=ww,height=hh,batch_size=1)[0]
 noise=invoke(registry,"RandomNoise",noise_seed=123456789)[0];sampler=invoke(registry,"KSamplerSelect",sampler_name="euler")[0]
 guider=invoke(registry,"CFGGuider",model=unet,positive=pos,negative=neg,cfg=1.0)[0]
 out=invoke(registry,"SamplerCustomAdvanced",noise=noise,guider=guider,sampler=sampler,sigmas=sigmas,latent_image=latent)[0]
 image=invoke(registry,"VAEDecode",samples=out,vae=vae)[0][0].detach().cpu().numpy()[...,:3]
 return cv2.resize(np.rint(image*255).clip(0,255).astype(np.uint8),(w,h),interpolation=cv2.INTER_LANCZOS4)

def execute_components(rgb,plan,registry,font_paths,model,models):
 import torch
 try:
  from .auto_pipeline import invoke,require_visible_asset
  from .spatial import compact_asset
  from .exporter import _text_image
  from .bezier import mask_to_paths
 except ImportError:
  from auto_pipeline import invoke,require_visible_asset
  from spatial import compact_asset
  from exporter import _text_image
  from bezier import mask_to_paths
 h,w=rgb.shape[:2];assets=[];warnings=list(plan.get("warnings",[]));rows=plan["assets"]
 if len({a["id"] for a in rows})!=len(rows):raise ValueError("Duplicate component IDs")
 if len({a["z"] for a in rows})!=len(rows):raise ValueError("Duplicate component layer order")
 for row in sorted(rows,key=lambda a:a["z"]):
  x,y,r,b=row["box"]
  if any(type(n) is not int for n in row["box"]) or not 0<=x<r<=w or not 0<=y<b<=h:raise ValueError("Component outside canvas: "+row["id"])
  crop=rgb[y:b,x:r].copy();method=row["method"];entry={"kind":"bitmap","name":row["name"],"group":row.get("group","")}
  # All work is tight and local; native vector coordinates stay document-absolute.
  local=dict(row,box=[0,0,r-x,b-y])
  local["polygon"]=[[a-x,c-y] for a,c in row.get("polygon",[])]
  local["holes"]=[[[a-x,c-y] for a,c in hole] for hole in row.get("holes",[])]
  alpha=component_mask(r-x,b-y,local)
  if method=="text":
   if not font_paths:raise ValueError("No installed font for editable text")
   rgba,native=_text_image(dict(text=row["text"],box=[0,0,r-x,b-y],color=row["color"]),font_paths[0],r-x,b-y)
   native["transform"][4]+=x;native["transform"][5]+=y;entry.update(kind="text",text=native)
   warnings.append(row["name"]+"：字体为近似字体，需核对字形与排版")
  else:
   if method=="edited":
    crop=edit_container(crop,row["prompt"],registry,models);warnings.append(row["name"]+"：去子层模型补绘表面，非无损恢复")
   elif method=="biref":
    if model is None:raise ValueError("BiRefNet must be connected")
    out=invoke(registry,"RemoveBackground",bg_removal_model=model,image=torch.from_numpy(crop.astype(np.float32)/255).unsqueeze(0))[0]
    mat=out.detach().cpu().numpy().squeeze()
    if mat.shape!=crop.shape[:2]:raise ValueError("Mask size mismatch")
    alpha=np.rint(np.clip(mat,0,1)*alpha).astype(np.uint8)
   elif method=="shape":
    col=np.array(row["color"],float);distance=np.max(abs(crop.astype(float)-col),axis=2);alpha=np.rint(np.clip(1-distance/row.get("tolerance",55),0,1)*alpha).astype(np.uint8)
    binary=(alpha>=128).astype(np.uint8);paths,stats=mask_to_paths(binary,origin=(x,y),tolerance=.3,smooth_pixels=0,minimum_area=.25,preserve_corners=True)
    if not paths:
     # Model colors are estimates. Calibrate only within its stated tolerance,
     # with clear separation from the surrounding surface; never expand ROI.
     tolerance=row.get("tolerance",55)
     candidates=(distance<tolerance)
     border=np.concatenate([crop[0],crop[-1],crop[:,0],crop[:,-1]])
     surface=np.median(border,axis=0)
     if candidates.sum()>=4 and np.max(abs(surface-col))>2*tolerance:
      calibrated=np.median(crop[candidates],axis=0)
      delta=np.max(abs(crop.astype(float)-calibrated),axis=2)
      binary=((delta<tolerance/2)&candidates&(component_mask(r-x,b-y,local)>=128)).astype(np.uint8)
      paths,stats=mask_to_paths(binary,origin=(x,y),tolerance=.3,smooth_pixels=0,minimum_area=.25,preserve_corners=True)
      if paths:
       warnings.append(row['id']+': calibrated vector color from '+str(col.tolist())+' to '+str(calibrated.tolist()))
       col=calibrated
    if not paths:raise ValueError("Empty vector: "+row["id"])
    alpha=binary*255;crop[:]=col.astype(np.uint8);entry.update(kind="shape",shapes=paths,color=col.astype(int).tolist())
   elif method=="solid":
    alpha=np.where(alpha>127,255,0).astype(np.uint8);crop[:]=row["color"]
    paths,stats=mask_to_paths((alpha>0).astype(np.uint8),origin=(x,y),tolerance=.3,smooth_pixels=0,minimum_area=.25,preserve_corners=True)
    if not paths:raise ValueError("Empty solid vector")
    entry.update(kind="shape",shapes=paths,color=row["color"])
   elif method!="source":raise ValueError("Unsupported component method: "+method)
   if row.get("clear_boxes"):
    boxes=[[a-x,c-y,rr-x,bb-y] for a,c,rr,bb in row["clear_boxes"]]
    if any(not 0<=a<rr<=r-x or not 0<=c<bb<=b-y for a,c,rr,bb in boxes):raise ValueError("Child clearing outside component")
    crop=clean_surface(crop,boxes);warnings.append(row["name"]+"：子层区域做局部表面补全，需检查材质连续")
   rgba=np.dstack([crop,alpha])
  entry.update(rgba=rgba,left=x,top=y,asset_id=row["id"]);require_visible_asset(rgba,row["name"]);assets.append(compact_asset(entry))
  if row.get("occluded"):warnings.append(row["name"]+"：遮挡内容尚未证明恢复，需验收")
 # QPAutoPSD supplies the separately connected scenic background.
 return np.dstack([rgb.copy(),np.full((h,w),255,np.uint8)]),assets,warnings
