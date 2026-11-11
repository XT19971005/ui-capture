"""Register generated pixels against visible source detail; never fit completed alpha to a box."""
import base64,copy,io,math
from PIL import Image


def _complete_circle(reference,generated,target,node):
 """Place only independently verified, complete bright circular silhouettes."""
 import cv2
 import numpy as np
 def circles(mask):
  contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
  found=[]
  for contour in contours:
   area=cv2.contourArea(contour)
   if area<100 or len(contour)<20:continue
   bx,by,bw,bh=cv2.boundingRect(contour)
   if bx<=0 or by<=0 or bx+bw>=mask.shape[1] or by+bh>=mask.shape[0]:continue
   if min(bw,bh)/max(bw,bh)<.94:continue
   (cx,cy),radius=cv2.minEnclosingCircle(contour)
   radial=np.linalg.norm(contour[:,0,:]-[cx,cy],axis=1)
   if area/(math.pi*radius*radius)<.94 or np.percentile(abs(radial-radius),95)>max(1.2,radius*.035):continue
   if 4*math.pi*area/cv2.arcLength(contour,True)**2<.84:continue
   found.append((cx,cy,radius,area))
  return found
 ga=np.array(generated);objects=circles((ga[:,:,3]>=128).astype('uint8')*255)
 if len(objects)!=1:return None
 gx,gy,gr,area=objects[0]
 opaque=ga[ga[:,:,3]>=192,:3]
 if not len(opaque):return None
 color=np.median(opaque,axis=0)
 if color.min()<165 or color[0]<color[2]*1.02:return None
 x,y,w,h=(float(target[k]) for k in ('x','y','width','height'))
 if min(w,h)<16 or max(w,h)>256 or min(w,h)/max(w,h)<.8:return None
 pad=max(12,max(w,h)*.25);left=max(0,int(x-pad));top=max(0,int(y-pad))
 rgb=np.array(reference)[top:min(reference.height,math.ceil(y+h+pad)),left:min(reference.width,math.ceil(x+w+pad))].astype(float)
 distance=np.linalg.norm(rgb-color,axis=2);fits=[]
 for threshold in (60,75,90):
  mask=((distance<threshold)&(rgb.min(axis=2)>165)&(rgb[:,:,0]>rgb[:,:,2]*1.02)).astype('uint8')*255
  found=circles(mask)
  if len(found)!=1:return None
  cx,cy,radius,unused=found[0]
  if not .7<=2*radius/max(w,h)<=1.2 or math.hypot(cx+left-x-w/2,cy+top-y-h/2)>max(w,h)*.15:return None
  fits.append((cx+left,cy+top,radius))
 centers=np.array(fits)
 if np.ptp(centers,axis=0).max()>2:return None
 cx,cy,radius=centers.mean(axis=0);scale=float(radius/gr)
 if not .1<=scale<=10:return None
 result=copy.deepcopy(node)
 result.update(x=float(cx-gx*scale),y=float(cy-gy*scale),width=generated.width*scale,height=generated.height*scale,positionReviewRequired=False)
 result['registration']={'method':'source-complete-circle','status':'aligned','scale':scale,'sourceCircle':[float(cx),float(cy),float(radius)],'generatedCircle':[float(gx),float(gy),float(gr)],'thresholdStabilityPixels':float(np.ptp(centers,axis=0).max()),'rawWidth':generated.width,'rawHeight':generated.height,'previous':copy.deepcopy(node.get('registration',{}))}
 result['reviewIssue']='；'.join(n for n in node.get('reviewIssue','').split('；') if n and '返回画幅' not in n and '临时登记' not in n)
 return result


def _visible_template(reference,generated,target,node):
 """Conservative fallback: require near-identical source pixels, not box-fit evidence.

 Search uniform scale and translation only. All solid pixels must agree, so an
 occluded/completed object is intentionally rejected unless SIFT can place it.
 Only analysis copies are resized; the returned PNG is never touched.
 """
 import cv2
 import numpy as np
 alpha=np.array(generated.getchannel('A'))
 ys,xs=np.where(alpha>=192)
 if not len(xs):return None
 l,t,r,b=int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
 if min(r-l,b-t)<8:return None
 x,y,w,h=(float(target[k]) for k in ('x','y','width','height'))
 if min(w,h)<=0 or max(w,h)>256 or max(r-l,b-t)>768:return None
 # The box seeds the search, but no candidate is accepted on geometry alone.
 seed=min(w/(r-l),h/(b-t));prior=float(node['width'])/generated.width
 scales=sorted(set([prior]+[seed*float(v) for v in np.linspace(.65,1.55,73)]))
 pad=max(12,min(max(w,h)*.4,100))
 left,top=max(0,int(x-pad)),max(0,int(y-pad))
 right,bottom=min(reference.width,math.ceil(x+w+pad)),min(reference.height,math.ceil(y+h+pad))
 source=np.array(reference)[top:bottom,left:right].astype(np.float32)
 piece=np.array(generated)[t:b,l:r];candidates=[]
 for scale in scales:
  tw,th=round((r-l)*scale),round((b-t)*scale)
  if min(tw,th)<8 or tw>source.shape[1] or th>source.shape[0]:continue
  scale=(tw/(r-l)+th/(b-t))/2
  if abs(tw/(r-l)-th/(b-t))>scale*.025:continue
  sample=cv2.resize(piece,(tw,th),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
  mask=(sample[:,:,3]>=192).astype(np.uint8)*255
  if np.count_nonzero(mask)<45:continue
  rgb=sample[:,:,:3].astype(np.float32)
  # Flat colored shapes have no unique internal evidence. Their silhouette
  # cannot be verified against an unknown background by this test.
  pixels=rgb[mask>0]
  if float(np.std(pixels,axis=0).max())<12:continue
  scores=cv2.matchTemplate(source,rgb,cv2.TM_SQDIFF,mask=mask)
  scores=np.nan_to_num(scores,nan=1e30,posinf=1e30,neginf=1e30)
  # Keep separated local alternatives as well as the best candidate.
  for unused in range(3):
   value,unused,pt,unused=cv2.minMaxLoc(scores)
   error=math.sqrt(max(0,value)/(np.count_nonzero(mask)*3))
   if error>12:break
   ox,oy=left+pt[0],top+pt[1]
   candidates.append((error,scale,ox-l*scale,oy-t*scale,ox,oy,tw,th))
   xx,yy=pt;radius=max(3,round(min(tw,th)*.18))
   scores[max(0,yy-radius):yy+radius+1,max(0,xx-radius):xx+radius+1]=1e30
 if not candidates:return None
 candidates.sort();best=candidates[0]
 if best[0]>9:return None
 # Reject a different placement/size with essentially the same source evidence.
 for other in candidates[1:]:
  distinct=abs(other[1]/best[1]-1)>.12 or math.hypot(other[4]-best[4],other[5]-best[5])>max(5,min(best[6:])*.2)
  if distinct and other[0]<best[0]+3:return None
 result=copy.deepcopy(node)
 result.update(x=best[2],y=best[3],width=generated.width*best[1],height=generated.height*best[1],positionReviewRequired=False)
 result['registration']={'method':'source-visible-template','status':'aligned','scale':best[1],'pixelRMSError':round(best[0],3),'rawWidth':generated.width,'rawHeight':generated.height,'previous':copy.deepcopy(node.get('registration',{}))}
 result['reviewIssue']='；'.join(n for n in node.get('reviewIssue','').split('；') if n and '返回画幅' not in n and '临时登记' not in n)
 return result


def calibrate(source,node,target):
 """Return placement only. Keep PNG bytes, including inferred parts and faint alpha, intact."""
 result=copy.deepcopy(node)
 previous=copy.deepcopy(node.get('registration',{}))
 def uncertain(reason):
  try:
   fallback=_complete_circle(reference,generated,target,node)
   if fallback is None:fallback=_visible_template(reference,generated,target,node)
   if fallback is not None:return fallback
  except Exception:pass
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


def annotation_estimate(generated,target,node):
 """Explicit proportional placement estimate; never masquerades as pixel alignment."""
 import numpy as np
 from scipy import ndimage
 alpha=np.asarray(generated.convert('RGBA'))[:,:,3]
 mask=alpha>=128;labels,count=ndimage.label(mask)
 if not count:raise ValueError('素材没有可识别主体')
 areas=np.bincount(labels.ravel());areas[0]=0;largest=int(areas.max())
 # Keep substantial separated parts (eyes, supports, ornaments), not faint noise.
 keep=np.where(areas>=max(3,largest*.002))[0];keep=keep[keep!=0]
 ys,xs=np.where(np.isin(labels,keep))
 l,t,r,b=int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
 x,y,w,h=[float(target[k]) for k in ('x','y','width','height')]
 scale=min(w/(r-l),h/(b-t))
 if not math.isfinite(scale) or scale<=0:raise ValueError('标注大小无效')
 result=copy.deepcopy(node)
 result.update(x=x+(w-(r-l)*scale)/2-l*scale,y=y+(h-(b-t)*scale)/2-t*scale,width=generated.width*scale,height=generated.height*scale,positionReviewRequired=True)
 result['registration']={'method':'annotation-proportional-estimate','status':'estimated','scale':scale,'targetBox':dict(target),'subjectBox':[l,t,r-l,b-t],'reason':'按对应标注等比估算大小与位置；不是像素级匹配'}
 return result


def background_frame(generated,box,node):
 """Cover the actual source content frame, not transparent workspace padding."""
 x,y,w,h=[float(v) for v in box]
 scale=max(w/generated.width,h/generated.height)
 result=copy.deepcopy(node);width=generated.width*scale;height=generated.height*scale
 result.update(x=x+(w-width)/2,y=y+(h-height)/2,width=width,height=height,positionReviewRequired=True)
 result['registration']={'method':'source-content-frame-cover','status':'estimated','sourceContentFrame':[x,y,w,h],'scale':scale,'reason':'按原图有效画幅等比覆盖；保留完整图片，不拉伸裁切，不代表构图逐点匹配'}
 return result
