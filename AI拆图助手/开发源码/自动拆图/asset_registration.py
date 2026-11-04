"""Register generated pixels against visible source detail; never fit completed alpha to a box."""
import base64,copy,io,math
from PIL import Image


def calibrate(source,node,target):
 """Return placement only. Keep PNG bytes, including inferred parts and faint alpha, intact."""
 result=copy.deepcopy(node)
 previous=copy.deepcopy(node.get('registration',{}))
 def uncertain(reason):
  result['positionReviewRequired']=True
  note='自动校对大小未通过：'+reason+'；保留原落位，请预览校对'
  result['reviewIssue']='；'.join(filter(None,[node.get('reviewIssue'),note]))
  result['registration']={'method':'source-visible-features','status':'needs-review','reason':reason,'previous':previous}
  return result
 try:
  import cv2
  import numpy as np
  if isinstance(source,Image.Image):reference=source.convert('RGB')
  else:
   with Image.open(source) as im:reference=im.convert('RGB')
  with Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1]))) as im:generated=im.convert('RGBA')
  # Searching only the intended object prevents identical neighbouring flowers
  # from winning a full-scene match. The box constrains evidence, not output size.
  x,y,w,h=(float(target[k]) for k in ('x','y','width','height'))
  pad=max(8,min(w,h)*.08)
  left,top=max(0,int(x-pad)),max(0,int(y-pad))
  right,bottom=min(reference.width,math.ceil(x+w+pad)),min(reference.height,math.ceil(y+h+pad))
  if right-left<16 or bottom-top<16:return uncertain('原图可见区域过小')
  roi=reference.crop((left,top,right,bottom))
  # Bound feature work without changing stored/generated image pixels.
  gs=min(1,1800/max(generated.size));rs=min(1,1800/max(roi.size))
  ga=np.array(generated.resize((max(1,round(generated.width*gs)),max(1,round(generated.height*gs)))))
  ra=np.array(roi.resize((max(1,round(roi.width*rs)),max(1,round(roi.height*rs)))))
  sift=cv2.SIFT_create(nfeatures=6000)
  kg,dg=sift.detectAndCompute(cv2.cvtColor(ga[:,:,:3],cv2.COLOR_RGB2GRAY),(ga[:,:,3]>=32).astype('uint8')*255)
  kr,dr=sift.detectAndCompute(cv2.cvtColor(ra,cv2.COLOR_RGB2GRAY),None)
  if dg is None or dr is None or min(len(kg),len(kr))<8:return uncertain('可对应的纹理不足')
  matches=cv2.BFMatcher().knnMatch(dg,dr,k=2)
  good=[pair[0] for pair in matches if len(pair)==2 and pair[0].distance<.7*pair[1].distance]
  # Enforce one-to-one evidence rather than counting duplicate descriptors.
  unique={}
  for match in sorted(good,key=lambda m:m.distance):unique.setdefault(match.trainIdx,match)
  good=list(unique.values())
  if len(good)<8:return uncertain('可靠对应点不足8个')
  gp=np.float32([kg[m.queryIdx].pt for m in good])/gs
  rp=np.float32([kr[m.trainIdx].pt for m in good])/rs+np.float32([left,top])
  matrix,inliers=cv2.estimateAffinePartial2D(gp,rp,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=4000,confidence=.995)
  if matrix is None:return uncertain('无法确定一致的比例与位置')
  selected=inliers.ravel().astype(bool);count=int(selected.sum());ratio=count/len(good)
  scale=float(math.hypot(matrix[0,0],matrix[1,0]));angle=float(math.degrees(math.atan2(matrix[1,0],matrix[0,0])))
  points=rp[selected];span=np.ptp(points,axis=0)
  if count<8 or ratio<.65 or min(span)<12 or span[0]*span[1]<w*h*.025:return uncertain('匹配证据不够分散或存在歧义')
  if not .1<=scale<=10 or abs(angle)>1:return uncertain('生成对象朝向或比例变化过大')
  # No rotation is introduced: fit scale+translation explicitly to reliable
  # inliers and reject any error that a rotation would otherwise conceal.
  a=gp[selected];b=rp[selected];ac=a-a.mean(axis=0);bc=b-b.mean(axis=0)
  scale=float((ac*bc).sum()/(ac*ac).sum());offset=b.mean(axis=0)-scale*a.mean(axis=0)
  residual=np.linalg.norm(scale*a+offset-b,axis=1);error=float(np.percentile(residual,90))
  if error>3 or not .1<=scale<=10:return uncertain('原图可见细节对齐误差过大')
  result.update(x=float(offset[0]),y=float(offset[1]),width=generated.width*scale,height=generated.height*scale,positionReviewRequired=False)
  result['registration']={'method':'source-visible-features','status':'aligned','scale':scale,'matches':len(good),'inliers':count,'inlierRatio':round(ratio,4),'errorPixels90':round(error,3),'rawWidth':generated.width,'rawHeight':generated.height,'previous':previous}
  # Boundary and visual-quality warnings remain independent of placement.
  if previous.get('method','').startswith('reference-'):
   notes=[n for n in node.get('reviewIssue','').split('；') if n and '返回画幅' not in n and '临时登记' not in n]
   result['reviewIssue']='；'.join(notes)
  return result
 except Exception:return uncertain('图像或匹配环境不可用')
