"""Evidence-based placement corrections; never infer geometry from layer names."""
import base64,io,math
from PIL import Image
from design_properties import obj,nullable,NUMBER

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
