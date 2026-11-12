"""ComfyUI adapter for Shijie's existing, pinned contracts.
Validation requires supplied real observations; it does not perform vision.
"""
import hashlib,re
import numpy as np
try:
 from .shijie_source.ui_components import validate_plan as _validate_ui
 from .shijie_source.acceptance_rules import ASSET_CRITERIA,FINAL_CRITERIA,check_errors
except ImportError:
 from shijie_source.ui_components import validate_plan as _validate_ui
 from shijie_source.acceptance_rules import ASSET_CRITERIA,FINAL_CRITERIA,check_errors

def validate_ui_structure(plan):
 if not isinstance(plan,dict) or any(not isinstance(plan.get(key),list) for key in ('assets','texts','vectors','uiComponents','uiReuseGroups')):
  raise ValueError('须保留拾界完整源清单及组件/复用数组，缺失不能当作空数组')
 return _validate_ui(plan)

def asset_digest(rgba):
 array=np.asarray(rgba)
 if array.dtype!=np.uint8 or array.ndim!=3 or array.shape[2]!=4 or min(array.shape[:2])<1:raise ValueError('验收绑定须使用实际uint8 RGBA像素')
 return hashlib.sha256(str(array.shape).encode('ascii')+b'\0'+array.tobytes()).hexdigest()

def verify_asset_review(rgba,review,source_sha256):
 if not isinstance(source_sha256,str) or not re.fullmatch('[0-9a-f]{64}',source_sha256):raise ValueError('缺少原图摘要')
 if not isinstance(review,dict) or review.get('status')!='PASS' or review.get('visual_reviewed') is not True:raise ValueError('没有已实际看图的PASS记录，禁止验收通过')
 if review.get('source_sha256')!=source_sha256 or review.get('asset_sha256')!=asset_digest(rgba):raise ValueError('素材/原图已变化，不能复用旧验收')
 checks=review.get('checks')
 if not isinstance(checks,list) or any(not isinstance(row,dict) for row in checks):raise ValueError('逐项验收记录无效')
 if review.get('issues')!=[]:raise ValueError('仍存在问题或缺少问题清单，禁止验收通过')
 errors=check_errors(checks,ASSET_CRITERIA)
 if errors:raise ValueError('；'.join(errors))
 return {'status':'PASS','asset_sha256':asset_digest(rgba),'source_sha256':source_sha256,'checks':checks,'scope':'single asset only; not final scene acceptance'}

def validate_instance_reviews(images,instances,reviews,source_sha256,current_original=None):
 if not isinstance(instances,list) or not isinstance(reviews,list):raise ValueError('实例和素材验收记录须为列表')
 if not instances:return []
 if current_original is None or asset_digest(current_original)!=source_sha256:raise ValueError('当前原图像素与验收来源不符，禁止复用旧验收')
 by_index={}
 for review in reviews:
  if not isinstance(review,dict) or type(review.get('source_index')) is not int or review['source_index'] in by_index:raise ValueError('素材验收索引无效或重复')
  by_index[review['source_index']]=review
 result=[];seen=set()
 for item in instances:
  index=item.get('source_index') if isinstance(item,dict) else None
  if type(index) is not int or not 0<=index<len(images) or index not in by_index:raise ValueError('复制源缺少匹配的实际素材验收记录')
  if index not in seen:result.append(verify_asset_review(images[index],by_index[index],source_sha256));seen.add(index)
 return result
