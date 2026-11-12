"""CPU OCR adapter. Import and model initialization are lazy, never at node registration."""
import numpy as np
try:
    from .core import estimate_ink
except ImportError:
    from core import estimate_ink

_engine=None


def analyze(rgb,minimum_score=.85):
    global _engine
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        raise RuntimeError('Automatic OCR requires rapidocr-onnxruntime; install requirements.txt in the ComfyUI Python environment') from e
    if _engine is None:_engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    rgb=np.asarray(rgb,dtype='uint8')[...,:3];height,width=rgb.shape[:2]
    # RapidOCR ndarray convention is OpenCV BGR.
    result,_=_engine(rgb[...,::-1].copy())
    texts=[];warnings=[];candidates=[]
    for quad,text,score in result or []:
        points=np.array(quad);x=max(0,int(np.floor(points[:,0].min())));y=max(0,int(np.floor(points[:,1].min())))
        right=min(width,int(np.ceil(points[:,0].max())));bottom=min(height,int(np.ceil(points[:,1].max())))
        if right<=x or bottom<=y:continue
        box=[x,y,right,bottom]
        if float(score)<minimum_score:
            warnings.append(f'低置信度文字未自动重建：{text} ({float(score):.3f})')
            candidates.append({'text':text,'box':box,'score':round(float(score),4),'reason':'LOW_CONFIDENCE','rebuild_allowed':False});continue
        if abs(points[1,1]-points[0,1])>max(2,.08*(right-x)):
            warnings.append(f'斜排文字暂保留位图：{text}');continue
        texts.append({'text':text,'box':box,'score':round(float(score),4),'color':estimate_ink(rgb,box),
            'font_match':'UNVERIFIED','content_review':'REQUIRED'})
    return {'format':'shijie-native-plan-v1','width':width,'height':height,'texts':texts,
        'warnings':warnings,'review_candidates':candidates,'visual_review':'REQUIRED','note':'仅自动OCR定位；实体拆分由上游分层模型完成，字体与语义分类未自动确认；低分候选仅供校对，不自动重建'}
