"""Evidence-based placement corrections; never infer geometry from layer names."""
import base64,hashlib,io,math
from PIL import Image
from design_properties import obj,nullable,NUMBER

def align_to_source(source,node):
 """Recover display geometry from matching pixels; never rewrite asset pixels."""
 import cv2,numpy as np
 box=[node.get(k) for k in ('x','y','width','height')]
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in box) or min(box[2:])<=0:
  raise ValueError('原图对齐坐标无效')
 if node.get('type')!='image' or node.get('assetKind')=='background':return None
 with Image.open(source) as original,Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1],validate=True))) as asset:
  if any(max(im.size)>6000 or im.width*im.height>6000000 for im in (original,asset)):raise ValueError('原图对齐图片超过容量限制')
  reference=np.array(original.convert('L'));rgba=np.array(asset.convert('RGBA'))
 ih,iw=rgba.shape[:2];sh,sw=reference.shape
 x,y,w,h=box;pad=max(w,h)*.5
 left,top=max(0,int(x-pad)),max(0,int(y-pad));right,bottom=min(sw,int(x+w+pad)),min(sh,int(y+h+pad))
 if right<=left or bottom<=top:return None
 mask=np.zeros_like(reference);mask[top:bottom,left:right]=255
 alpha=cv2.erode((rgba[:,:,3]>220).astype('uint8')*255,np.ones((9,9),np.uint8))
 detector=cv2.SIFT_create(nfeatures=6000)
 a,da=detector.detectAndCompute(cv2.cvtColor(rgba,cv2.COLOR_RGBA2GRAY),alpha)
 b,db=detector.detectAndCompute(reference,mask)
 if da is None or db is None or min(len(a),len(b))<12:return None
 pairs=[row[0] for row in cv2.BFMatcher().knnMatch(da,db,k=2) if len(row)==2 and row[0].distance<.65*row[1].distance]
 # Repeated texture must not count several matches to one source landmark.
 unique={}
 for pair in sorted(pairs,key=lambda p:p.distance):unique.setdefault(pair.trainIdx,pair)
 pairs=list(unique.values())
 if len(pairs)<12:return None
 aa=np.float32([a[p.queryIdx].pt for p in pairs]);bb=np.float32([b[p.trainIdx].pt for p in pairs])
 matrix,inside=cv2.estimateAffine2D(aa,bb,method=cv2.RANSAC,ransacReprojThreshold=4,maxIters=5000,confidence=.999)
 if matrix is None:return None
 keep=inside.ravel().astype(bool);count=int(keep.sum())
 if count<12 or count/len(pairs)<(.5 if count>=40 else .6):return None
 aa,bb=aa[keep],bb[keep]
 if np.min(np.ptp(bb,axis=0))<8 or np.any(np.ptp(aa,axis=0)<np.array([iw,ih])*.1):return None
 shear=max(abs(matrix[0,1]/matrix[0,0]),abs(matrix[1,0]/matrix[1,1])) if min(matrix[0,0],matrix[1,1])>0 else math.inf
 if shear>.15 or np.linalg.det(matrix[:,:2])<=0:return None
 sx,tx=np.linalg.lstsq(np.column_stack((aa[:,0],np.ones(count))),bb[:,0],rcond=None)[0]
 sy,ty=np.linalg.lstsq(np.column_stack((aa[:,1],np.ones(count))),bb[:,1],rcond=None)[0]
 if min(sx,sy)<=0 or not .8<sx/sy<1.25:return None
 errors=np.linalg.norm(aa*np.array([sx,sy])+np.array([tx,ty])-bb,axis=1)
 if np.percentile(errors,90)>4 or shear>.03:
  errors=np.linalg.norm(aa@matrix[:,:2].T+matrix[:,2]-bb,axis=1)
  if np.percentile(errors,90)>4:return None
  corners=np.array([[0,0],[iw,0],[iw,ih],[0,ih]])@matrix[:,:2].T+matrix[:,2]
  left,top=np.floor(corners.min(axis=0)).astype(int);right,bottom=np.ceil(corners.max(axis=0)).astype(int)
  ow,oh=int(right-left),int(bottom-top)
  if min(ow,oh)<1 or max(ow,oh)>6000 or ow*oh>6000000 or left>=sw or top>=sh or right<=0 or bottom<=0:return None
  inverse=np.linalg.inv(np.vstack((matrix,[0,0,1])))
  inverse[:2,2]+=inverse[:2,:2]@np.array([left,top])
  # Pillow handles premultiplied alpha. Keep the full transformed canvas,
  # including unseen feet; never crop the result back to the source image.
  transformed=Image.fromarray(rgba).transform((ow,oh),Image.Transform.AFFINE,tuple(inverse[:2].ravel()),Image.Resampling.BICUBIC)
  output=io.BytesIO();transformed.save(output,'PNG')
  return {**node,'x':int(left),'y':int(top),'width':ow,'height':oh,'src':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),
          'sourceAlignment':{'method':'SIFT-RANSAC-affine','pixelWarp':True,'matrix':matrix.tolist(),'inliers':count,'matches':len(pairs),
                             'medianErrorPx':float(np.median(errors)),'p90ErrorPx':float(np.percentile(errors,90)),
                             'inputSHA256':hashlib.sha256(base64.b64decode(node['src'].split(',',1)[1],validate=True)).hexdigest()}}
 width,height=iw*sx,ih*sy
 if min(width,height)<1 or max(width,height)>6000 or width*height>6000000 or tx>=sw or ty>=sh or tx+width<=0 or ty+height<=0:return None
 # ponytail: bounded small affine corrections only. Perspective/redesigned or
 # featureless assets still require visual review, never invented landmarks.
 return {**node,'x':float(tx),'y':float(ty),'width':float(width),'height':float(height),
         'sourceAlignment':{'method':'SIFT-RANSAC','inliers':count,'matches':len(pairs),'medianErrorPx':float(np.median(errors)),'p90ErrorPx':float(np.percentile(errors,90))}}

PLACEMENT=nullable(obj({**{k:NUMBER for k in ('x','y','width','height','confidence')},'evidence':{'type':'string'},'contentCorrect':{'type':'boolean'}}))
PLACEMENT_PROMPT='逐项核对原图中物体的绝对尺寸和位置，不把当前错误图层框当原图标准。placement仅在有明确视觉证据需改大小/位置时填写，否则null；x/y/width/height指完整实体可见alpha轮廓的画布绝对包围框，不含透明留白。画布边缘截断的完整物体可延伸到画布外，不能把完整扇子压进原图仅露出的局部框；被其他物体遮挡部分须依据完整实体估计，不确定则placement=null并NEEDS_REVIEW。confidence须>=0.9且evidence说明对应轮廓/地标；contentCorrect仅当当前素材像素的身份、形状、颜色和边缘均正确、只需几何调整时true。不得用未选物体的框代替。'

def validate_placement(value,scene,region=None):
 keys={'x','y','width','height','confidence','evidence','contentCorrect'}
 if not isinstance(value,dict) or set(value)!=keys:raise ValueError('尺寸校对缺少明确证据')
 if any(isinstance(value[k],bool) or not isinstance(value[k],(int,float)) or not math.isfinite(value[k]) for k in ('x','y','width','height','confidence')):raise ValueError('尺寸校对坐标无效')
 x,y,w,h=(value[k] for k in ('x','y','width','height'))
 if not .9<=value['confidence']<=1 or not isinstance(value['evidence'],str) or not 8<=len(value['evidence'].strip())<=2000 or not isinstance(value['contentCorrect'],bool):raise ValueError('尺寸校对证据不足')
 if min(w,h)<1 or max(w,h)>6000 or w*h>6000000 or x>=scene['width'] or y>=scene['height'] or x+w<=0 or y+h<=0:raise ValueError('尺寸校对超出有效画布范围')
 if region is not None:
  from region_refine import contains
  if not contains(region,value):raise ValueError('尺寸校对跨出用户确认区域')
 return dict(value)

def correct_placement(node,value,scene,region=None):
 p=validate_placement(value,scene,region)
 with Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1]))) as image:
  iw,ih=image.size;alpha=image.convert('RGBA').getchannel('A').getbbox()
 if not alpha:raise ValueError('素材完全透明，无法尺寸校对')
 left,top,right,bottom=alpha;vw,vh=right-left,bottom-top
 scale=min(p['width']/vw,p['height']/vh)
 result={**node,'x':p['x']+(p['width']-vw*scale)/2-left*scale,'y':p['y']+(p['height']-vh*scale)/2-top*scale,'width':iw*scale,'height':ih*scale}
 if max(result['width'],result['height'])>6000 or result['width']*result['height']>6000000:raise ValueError('透明画布尺寸过大，无法安全校对')
 if region is not None:
  from region_refine import contains
  if not contains(region,result):raise ValueError('完整素材画布跨出用户确认区域')
 result['placementReview']={'confidence':p['confidence'],'evidence':p['evidence'],'sourceBounds':{k:p[k] for k in ('x','y','width','height')}}
 return result

def extraction_bounds(node):
 """A regenerated asset must retain its visible world bounds across retries."""
 if node.get('_placementBounds') is not None:return [node['_placementBounds'][k] for k in ('x','y','width','height')]
 x,y,w,h=(node[k] for k in ('x','y','width','height'))
 if not node.get('src'):return [x,y,w,h]
 with Image.open(io.BytesIO(base64.b64decode(node['src'].split(',',1)[1]))) as image:
  iw,ih=image.size;alpha=image.convert('RGBA').getchannel('A').getbbox()
 if not alpha:raise ValueError('旧素材完全透明，不能据此推断提取尺寸')
 left,top,right,bottom=alpha
 return [x+left*w/iw,y+top*h/ih,(right-left)*w/iw,(bottom-top)*h/ih]
