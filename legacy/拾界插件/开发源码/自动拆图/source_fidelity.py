"""Calibrate observed pixels separately from inferred, occluded material."""
import base64
import hashlib
import io
import math

import cv2
import numpy as np
from PIL import Image


def matte_against_background(observed, background, foreground_hint):
    """Estimate soft alpha with inspected background/foreground colour evidence.

    This is colour-line matting, not a semantic segmenter. Callers must bound
    the selected object and inspect the result on contrasting backgrounds.
    """
    arrays = [np.asarray(value, dtype=np.float32) for value in (observed, background, foreground_hint)]
    shape = arrays[0].shape
    if (len(shape) != 3 or shape[2] != 3 or not 1 <= shape[0]*shape[1] <= 6000000
            or max(shape[:2]) > 6000 or any(a.shape != shape or not np.isfinite(a).all()
            or (a < 0).any() or (a > 255).any() for a in arrays)):
        raise ValueError('软边校准要求尺寸一致、有效的 RGB 图像')
    observed, background, hint = arrays
    difference = observed-background; direction = hint-background
    alpha = np.sum(difference*direction, axis=2)/np.maximum(1, np.sum(direction**2, axis=2))
    minimum = np.max(np.where(difference >= 0, difference/np.maximum(1, 255-background),
                              -difference/np.maximum(1, background)), axis=2)
    alpha = np.clip(np.maximum(alpha, minimum), 0, 1)
    alpha[np.max(np.abs(difference), axis=2) <= 2] = 0
    foreground = np.clip(background+difference/np.maximum(alpha[:, :, None], 1/255), 0, 255)
    foreground[alpha == 0] = 0
    return np.dstack((np.rint(foreground).astype(np.uint8), np.rint(alpha*255).astype(np.uint8)))


def contour_mask(rgb, polygon, radius=8):
    """An explicit contour seeds local edge refinement; it is not object recognition."""
    h, w = rgb.shape[:2]
    points = np.asarray(polygon, dtype=np.float64)
    if (points.ndim != 2 or points.shape[1] != 2 or not 3 <= len(points) <= 256
            or not np.isfinite(points).all() or (points < 0).any()
            or (points[:, 0] >= w).any() or (points[:, 1] >= h).any()):
        raise ValueError('保真轮廓须为原图内的 3–256 个有限坐标')
    if type(radius) is not int or not 0 <= radius <= 32:
        raise ValueError('轮廓校准范围须为 0–32 像素')
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [np.rint(points).astype(np.int32)], 255)
    if np.count_nonzero(mask) < 16:
        raise ValueError('保真轮廓面积过小')
    if not radius:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
    inner = cv2.erode(mask, kernel)
    outer = cv2.dilate(mask, kernel)
    if not inner.any() or not (outer == 0).any():
        raise ValueError('轮廓校准缺少明确的前景或背景种子')
    labels = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    labels[inner > 0] = cv2.GC_FGD
    labels[outer == 0] = cv2.GC_BGD
    # ponytail: existing OpenCV refines only a <=32 px band. Occlusion/soft hair
    # still needs an inspected contour; do not claim automatic semantic matting.
    # ponytail: each job owns a process; if segmentation moves to threads,
    # serialize this OpenCV RNG + GrabCut pair to keep repeatable masks.
    cv2.setRNGSeed(0)
    cv2.grabCut(rgb, labels, None, np.zeros((1, 65)), np.zeros((1, 65)), 4, cv2.GC_INIT_WITH_MASK)
    foreground=((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)).astype(np.uint8)
    _,components=cv2.connectedComponents(foreground,connectivity=8)
    anchors=np.unique(components[inner>0]);anchors=anchors[anchors!=0]
    return np.where(np.isin(components,anchors),255,0).astype(np.uint8)

def restore_visible(source, node, polygon, *, exclusions=(), radius=8, preserve_outline=False,
                    match_color=False, feather=0, protected=(), clip_to_source=False, lock_observed_outline=False, holes=(), matte_edges=False, occlusion_feather=0):
    with Image.open(source) as image:
        if max(image.size) > 6000 or image.width*image.height > 6000000:
            raise ValueError('保真原图超过容量限制')
        if image.convert('RGBA').getchannel('A').getextrema() != (255, 255):
            raise ValueError('当前保真校准要求不透明原图')
        rgb = np.asarray(image.convert('RGB'))
    if not isinstance(exclusions, (list, tuple)) or len(exclusions) > 32:
        raise ValueError('遮挡轮廓最多 32 项')
    if not isinstance(holes,(list,tuple)) or len(holes)>32:raise ValueError('透明孔洞最多 32 项')
    if any(type(v) is not bool for v in (preserve_outline,match_color,clip_to_source,lock_observed_outline,matte_edges)) or type(feather) is not int or not 0 <= feather <= 32:
        raise ValueError('保真边缘或颜色参数无效')
    if type(occlusion_feather) is not int or not 0<=occlusion_feather<=128:raise ValueError('遮挡接缝过渡须为 0–128 像素')
    if not isinstance(protected,(list,tuple)) or len(protected)>32:
        raise ValueError('保真保护区域最多 32 项')
    mask = contour_mask(rgb, polygon, radius)
    for points in holes:mask[contour_mask(rgb,points,0)>0]=0
    if not mask.any():raise ValueError('孔洞不能抹除整个素材')
    occluded = np.zeros(mask.shape, np.uint8)
    for points in exclusions:
        occluded = np.maximum(occluded, contour_mask(rgb, points, 0))
    locked_pixels = np.zeros(mask.shape,np.uint8)
    for points in protected:
        locked_pixels = np.maximum(locked_pixels,contour_mask(rgb,points,0))
    # Explicit observed regions take priority over padded occlusion boundaries.
    occluded[locked_pixels > 0] = 0
    geometry = [node.get(k) for k in ('x', 'y', 'width', 'height')]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in geometry):
        raise ValueError('保真素材坐标无效')
    x, y, w, h = geometry
    if min(w, h) < 1 or max(w, h) > 6000 or w*h > 6000000:
        raise ValueError('保真素材尺寸无效')
    raw = base64.b64decode(node['src'].split(',', 1)[1], validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if max(image.size) > 6000 or image.width*image.height > 6000000:
            raise ValueError('保真底稿超过容量限制')
        generated = np.asarray(image.convert('RGBA'))
    ys, xs = np.nonzero(mask)
    left, top = min(math.floor(x), int(xs.min())), min(math.floor(y), int(ys.min()))
    right, bottom = max(math.ceil(x+w), int(xs.max())+1), max(math.ceil(y+h), int(ys.max())+1)
    ow, oh = right-left, bottom-top
    if max(ow, oh) > 6000 or ow*oh > 6000000:
        raise ValueError('保真结果超过容量限制')
    sx,sy=w/generated.shape[1],h/generated.shape[0]
    # Pillow resamples RGBA in premultiplied alpha; independent RGBA channels
    # mix transparent black into coloured edges during fractional alignment.
    if sx==sy==1 and (x,y,ow,oh)==(left,top,generated.shape[1],generated.shape[0]):
        result=generated.copy()  # Identity resampling still rounds premultiplied soft RGB.
    else:
        result=np.asarray(Image.fromarray(generated).transform((ow,oh),Image.Transform.AFFINE,
                           (1/sx,0,(left-x)/sx,0,1/sy,(top-y)/sy),Image.Resampling.BICUBIC)).copy()
    sw, sh = rgb.shape[1], rgb.shape[0]
    l, t, r, b = max(0, left), max(0, top), min(sw, right), min(sh, bottom)
    if r <= l or b <= t:
        raise ValueError('保真素材与原图没有交集')
    dst = result[t-top:b-top, l-left:r-left]
    shape = mask[t:b, l:r]
    hidden = (occluded[t:b, l:r] > 0) & (shape > 0)
    if hidden.any():
        # Model contours are approximate at the join. Require the interior,
        # not every antialiased boundary pixel; full-asset QA still checks gaps.
        border=min(12,max(1,radius))
        core=cv2.erode(hidden.astype(np.uint8),np.ones((2*border+1,)*2,np.uint8))>0
        if not (dst[:,:,3][hidden]>=240).any() or (dst[:,:,3][core]<240).any():
            raise ValueError('遮挡区域缺少完整底稿，不能用原图遮挡物冒充补全')
    observed = (shape > 0) & ~hidden
    if not observed.any():
        raise ValueError('保真区域没有可观察像素')
    coefficients = []
    if match_color:
        eligible = observed & (dst[:, :, 3] >= 250)
        if eligible.sum() < 64:
            raise ValueError('颜色校准缺少不透明原图证据')
        for channel in range(3):
            a = dst[:, :, channel][eligible].astype(float)[::8]
            bgr = rgb[t:b, l:r, channel][eligible].astype(float)[::8]
            # ponytail: a median channel offset fixes exposure/white balance,
            # without fitting away material contrast. Relighting needs a new asset.
            gain, bias = 1, float(np.median(bgr-a))
            if not -80 <= bias <= 80:
                raise ValueError('颜色校准偏差过大，需要重新检查素材与原图位置')
            coefficients.append([float(gain), float(bias)])
            result[:, :, channel] = np.rint(np.clip(result[:, :, channel].astype(float)*gain+bias, 0, 255)).astype(np.uint8)
    weight = np.minimum(1, cv2.distanceTransform(np.pad(observed.astype(np.uint8),1), cv2.DIST_L2, 5)[1:-1,1:-1]/feather) if feather else observed.astype(float)
    join=occlusion_feather or (24 if match_color else 0)
    if occluded.any() and join:
        weight *= np.minimum(1,cv2.distanceTransform((occluded[t:b,l:r]==0).astype(np.uint8),cv2.DIST_L2,5)/join)
    if occlusion_feather:
        # Original canvas edges are also known-to-inferred joins when the
        # complete layer extends outside the uploaded image.
        if left<0:weight*=np.minimum(1,(np.arange(l,r)+1)/occlusion_feather)[None,:]
        if right>sw:weight*=np.minimum(1,(sw-np.arange(l,r))/occlusion_feather)[None,:]
        if top<0:weight*=np.minimum(1,(np.arange(t,b)+1)/occlusion_feather)[:,None]
        if bottom>sh:weight*=np.minimum(1,(sh-np.arange(t,b))/occlusion_feather)[:,None]
    weight[(locked_pixels[t:b,l:r]>0)&observed] = 1
    if lock_observed_outline:weight[observed & (dst[:,:,3]<240)] = 1
    if preserve_outline and not lock_observed_outline:
        # ponytail: source RGB contains the old background wherever alpha is
        # translucent. Copy only opaque evidence; recovering wrong glass alpha
        # still needs an actual matte, not another source-colour overwrite.
        weight[dst[:,:,3]<250] = 0
    dst[:, :, :3] = np.rint(dst[:, :, :3]*(1-weight[:, :, None]) + rgb[t:b, l:r]*weight[:, :, None]).astype(np.uint8)
    if not preserve_outline:
        result[:, :, 3] = 0
        dst[:, :, 3] = shape
    elif lock_observed_outline:
        # The source-visible envelope is known; extending it to the full asset
        # would delete unseen feet. Excluded occluders retain generated pixels.
        ml,mt,mr,mb=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
        region=result[mt-top:mb-top,ml-left:mr-left]
        # Model contours and occluder contours are independently rounded.
        # Keep the donor in their uncertain join instead of cutting a slit.
        band=max(4,radius)
        uncertain=cv2.dilate(occluded,np.ones((2*band+1,2*band+1),np.uint8))
        known=uncertain[mt:mb,ml:mr]==0
        region[:,:,3][known]=mask[mt:mb,ml:mr][known]
    if matte_edges:
        from scipy.ndimage import distance_transform_edt
        visible=np.where((mask>0)&(occluded==0),255,0).astype(np.uint8)
        kernel=np.ones((7,7),np.uint8);inner=cv2.erode(visible,kernel)
        outer=cv2.dilate(visible,kernel)
        band=(outer>0)&(inner==0)&(cv2.dilate(occluded,np.ones((2*max(4,radius)+1,)*2,np.uint8))==0)
        # The source canvas boundary is an unknown continuation, not a matte edge.
        band[:3]=False;band[-3:]=False;band[:,:3]=False;band[:,-3:]=False
        if inner.any() and band.any():
            # ponytail: estimate only a 3 px edge band from nearby source colours.
            # Broad smoke/translucency needs a dedicated matte, not this local fit.
            background=cv2.inpaint(rgb,outer,3,cv2.INPAINT_TELEA)
            _,nearest=distance_transform_edt(inner==0,return_indices=True)
            hint=rgb[nearest[0],nearest[1]]
            soft=matte_against_background(rgb,background,hint)
            local=band[t:b,l:r]
            dst[local]=soft[t:b,l:r][local]
    if clip_to_source:
        result = result[t-top:b-top,l-left:r-left].copy()
        left,top,ow,oh = l,t,r-l,b-t
    output = io.BytesIO(); Image.fromarray(result).save(output, 'PNG')
    value = output.getvalue()
    metadata = {k: v for k, v in node.items() if k not in ('visualCheck', 'reviewIssue', 'sourceAlignment')}
    return {**metadata, 'x': left, 'y': top, 'width': ow, 'height': oh,
            'src': 'data:image/png;base64,' + base64.b64encode(value).decode(),
            'provenance': 'source-visible-with-inferred-completion', 'review': True,
            'assetReviewStatus': 'NOT_REVIEWED',
            'sourceFidelity': {'sourceSHA256': hashlib.sha256(rgb.tobytes()).hexdigest(),
                               'priorAssetSHA256': hashlib.sha256(raw).hexdigest(),
                               'assetSHA256': hashlib.sha256(value).hexdigest(),
                               'observedPixels': int((weight == 1).sum()), 'hiddenCompletion': bool(hidden.any()),
                               'polygon': polygon, 'exclusions': exclusions, 'radius': radius,
                               'preserveOutline': preserve_outline, 'colorCoefficients': coefficients,
                               'matchColor': match_color, 'feather': feather,
                               'protected': protected, 'clipToSource': clip_to_source,
                               'lockObservedOutline': lock_observed_outline,'holes':holes,'matteEdges':matte_edges,'occlusionFeather':occlusion_feather}}


def reapply_calibration(source, previous, generated):
    """A later AI repair must not silently repaint inspected source detail."""
    calibration = previous.get('sourceFidelity')
    if not calibration:
        return generated
    with Image.open(source) as image:
        digest = hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
    if digest != calibration.get('sourceSHA256'):
        raise ValueError('保真校准的原图已变化，请重新检查轮廓；旧素材保留')
    if calibration.get('softEdgeCalibration'):
        raise ValueError('此素材包含已校准的软边，不能用普通重生成覆盖；旧素材保留，需结合背景重新校准')
    return restore_visible(source, generated, calibration['polygon'],
                           exclusions=calibration['exclusions'], radius=calibration['radius'],
                           preserve_outline=calibration['preserveOutline'],
                           match_color=calibration['matchColor'], feather=calibration['feather'],
                           protected=calibration.get('protected',()),clip_to_source=calibration.get('clipToSource',False),
                           lock_observed_outline=calibration.get('lockObservedOutline',False),holes=calibration.get('holes',()),matte_edges=calibration.get('matteEdges',False),occlusion_feather=calibration.get('occlusionFeather',0))
