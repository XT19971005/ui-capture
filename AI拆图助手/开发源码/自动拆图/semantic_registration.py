"""Semantic landmark registration when regenerated texture defeats pixel matching."""
import copy, math, tempfile
from pathlib import Path
from PIL import Image

SCHEMA={'type':'object','additionalProperties':False,'required':['sameObject','confidence','reason','anchors'],'properties':{'sameObject':{'type':'boolean'},'confidence':{'type':'number'},'reason':{'type':'string'},'anchors':{'type':'array','items':{'type':'object','additionalProperties':False,'required':['name','sourceX','sourceY','assetX','assetY'],'properties':{'name':{'type':'string'},'sourceX':{'type':'number'},'sourceY':{'type':'number'},'assetX':{'type':'number'},'assetY':{'type':'number'}}}}}}

def fit(analysis,source_box,asset_box,node,generated_size):
 import numpy as np
 if not isinstance(analysis,dict) or analysis.get('sameObject') is not True or not isinstance(analysis.get('confidence'),(int,float)) or analysis['confidence']<.85:raise ValueError('生成素材与原对象造型不一致或无法确认：'+str(analysis.get('reason','无法识别对应部位'))[:180]+'（置信度'+str(analysis.get('confidence','未知'))+'）')
 points=analysis.get('anchors',[])
 if not 3<=len(points)<=12:raise ValueError('可核对的对应部位不足3个')
 for p in points:
  if not all(type(p.get(k)) in (int,float) and math.isfinite(p[k]) and 0<=p[k]<=1000 for k in ('sourceX','sourceY','assetX','assetY')):raise ValueError('AI对应坐标无效')
 l,t,w,h=source_box;al,at,aw,ah=asset_box
 b=np.array([[l+p['sourceX']*w/1000,t+p['sourceY']*h/1000] for p in points]);a=np.array([[al+p['assetX']*aw/1000,at+p['assetY']*ah/1000] for p in points])
 ac=a-a.mean(axis=0);bc=b-b.mean(axis=0);den=float((ac*ac).sum())
 if den<=0 or min(np.ptp(a,axis=0))<min(aw,ah)*.15 or min(np.ptp(b,axis=0))<min(w,h)*.08:raise ValueError('对应部位过于集中，不能确定大小')
 scale=float((ac*bc).sum()/den);offset=b.mean(axis=0)-scale*a.mean(axis=0)
 errors=np.linalg.norm(scale*a+offset-b,axis=1);limit=max(3,min(w,h)*.045)
 if not .02<=scale<=20 or float(errors.max())>limit:raise ValueError('对应部位不能通过同一比例对齐，造型或朝向不一致')
 result=copy.deepcopy(node);result.update(x=float(offset[0]),y=float(offset[1]),width=generated_size[0]*scale,height=generated_size[1]*scale,positionReviewRequired=False)
 result['registration']={'method':'source-semantic-landmarks','status':'aligned','confidence':analysis['confidence'],'scale':scale,'errorPixelsMax':round(float(errors.max()),3),'anchors':points,'sourceCrop':source_box,'assetCrop':asset_box,'reason':analysis['reason']}
 return result

def calibrate_semantic(reference,generated,target,node,cancelled=lambda:False,on_status=None,analyze=None):
 import numpy as np
 from codex_client import CLIENT
 if on_status:on_status('正在对照原图与标注框识别对应部位…')
 x,y,w,h=[float(target[k]) for k in ('x','y','width','height')]
 pad=max(12,min(w,h)*.15);l=max(0,math.floor(x-pad));t=max(0,math.floor(y-pad));r=min(reference.width,math.ceil(x+w+pad));b=min(reference.height,math.ceil(y+h+pad))
 if r<=l or b<=t:raise ValueError('对应标注超出原图')
 alpha=np.asarray(generated.convert('RGBA'))[:,:,3];ys,xs=np.where(alpha>=128)
 if len(xs)<20:raise ValueError('生成素材没有可识别主体')
 al,at,ar,ab=int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
 # Analysis crops only; original PNG and low-alpha shadows remain intact.
 asset=generated.crop((al,at,ar,ab)).convert('RGBA');background=Image.new('RGBA',asset.size,'#777777');background.alpha_composite(asset)
 with tempfile.TemporaryDirectory(prefix='shijie-align-') as folder:
  a=Path(folder)/'source.png';c=Path(folder)/'asset.png';reference.crop((l,t,r,b)).convert('RGB').save(a);background.convert('RGB').save(c)
  prompt='对照两张附件为同一个对象确定排版大小与位置，不生图、不改造型。第一张是原画中的目标局部，第二张是生成后的完整独立素材。目标名称：'+str(target.get('name') or node.get('name'))+'。标注只指原图可见部分，补全处允许超出，不能把完整素材塞进可见框。仅当造型、朝向相符时sameObject=true；差异明显必须false。找3至8个双方确实可见的同名部位（尖顶、轮心、眼睛、拐角等），不要用两张图片四角或裁图边缘凑数，不使用原图被遮挡的推测部位。sourceX/Y与assetX/Y分别是各自附件画面内0至1000的坐标。对应点须分布在物体不同位置，供统一等比缩放和平移拟合。若要变形或旋转才能对应则拒绝。confidence是对应部位可靠度。reason简短中文说明造型或匹配依据。只返回JSON。'
  analysis=(analyze or CLIENT.analyze)(prompt,[a,c],SCHEMA,cancelled=cancelled,timeout=120,on_status=on_status)
 if cancelled():raise InterruptedError('已取消')
 return fit(analysis,(l,t,r-l,b-t),(al,at,ar-al,ab-at),node,generated.size)
