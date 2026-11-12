"""Deterministic native-layer planning; no network, filesystem or ComfyUI imports."""
import math
import re
from pathlib import Path
import cv2
import numpy as np
try:
    from .bezier import mask_to_paths
except ImportError:
    from bezier import mask_to_paths


def rgba_batch(images, masks=None):
    def array(value):
        return value.detach().cpu().numpy() if hasattr(value, 'detach') else np.asarray(value)
    images = array(images)
    if images.ndim != 4 or images.shape[-1] not in (3,4):
        raise ValueError('IMAGE must be BHWC RGB or RGBA')
    if not np.isfinite(images).all():
        raise ValueError('IMAGE contains nonfinite values')
    if masks is not None:
        masks = array(masks)
        if masks.ndim == 2: masks = masks[None]
        if masks.ndim != 3 or masks.shape[0] not in (1,len(images)) or masks.shape[1:] != images.shape[1:3]:
            raise ValueError('MASK dimensions/batch do not match IMAGE')
        if not np.isfinite(masks).all(): raise ValueError('MASK contains nonfinite values')
    result = []
    for i, image in enumerate(images):
        rgb = np.clip(np.rint(image[...,:3]*255),0,255).astype('uint8')
        alpha = np.clip(image[...,3],0,1) if image.shape[-1] == 4 else np.ones(image.shape[:2])
        if masks is not None: alpha = alpha * (1-np.clip(masks[0 if len(masks)==1 else i],0,1))
        result.append(np.dstack([rgb,np.rint(alpha*255).astype('uint8')]))
    return result


def validate_plan(plan, width, height):
    if not isinstance(plan,dict): raise ValueError('Plan must be a JSON object')
    if plan.get('width',width)!=width or plan.get('height',height)!=height:raise ValueError('Plan canvas differs from decoded layers; do not silently scale text boxes')
    rows = plan.get('texts',[])
    if not isinstance(rows,list) or len(rows)>500: raise ValueError('Invalid texts list')
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('text'),str) or not row['text'].strip():
            raise ValueError('Text must be a nonempty string')
        box=row.get('box',[])
        if len(box)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in box):
            raise ValueError('Text box must contain four finite coordinates')
        x,y,r,b=box
        if not (0<=x<r<=width and 0<=y<b<=height): raise ValueError('Text box outside image')
        if 'font_file' in row: raise ValueError('Font files belong in the explicit font input, not expert JSON')
        if 'color' in row and (len(row['color'])!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=255 for v in row['color'])):
            raise ValueError('Text color must be three RGB values')
    return plan


def estimate_ink(rgb, box):
    x,y,r,b=map(int,box);crop=np.asarray(rgb)[y:b,x:r,:3]
    # Use the crop boundary as a background estimate: glyphs may be light or dark,
    # and thick glyphs may occupy most of the interior. Complex art still needs review.
    border=np.concatenate([crop[0],crop[-1],crop[:,0],crop[:,-1]])
    background=np.median(border,axis=0)
    flat=crop.reshape(-1,3);distance=np.max(abs(flat.astype(float)-background),axis=1)
    # Near-white UI glyphs can have a darker, higher-contrast drop shadow.
    # Prefer a substantial bright stroke population over that shadow on a mid/dark
    # panel. This remains a colour estimate, never approval of decorated text.
    bright=(flat.mean(axis=1)>=225)&(flat.min(axis=1)>=200)
    if background.mean()<190 and bright.sum()>=max(8,len(flat)*.02):
        return np.median(flat[bright],axis=0).astype(int).tolist()
    peak=float(distance.max())
    if peak<3:return np.median(flat,axis=0).astype(int).tolist()
    ink=flat[distance>=max(3,peak*.8)]
    return np.median(ink,axis=0).astype(int).tolist()


def clear_text(rgba, row):
    """Remove only colour-matching pixels inside a confirmed text box."""
    result=rgba.copy();x,y,r,b=map(int,row['box']);crop=result[y:b,x:r]
    colour=np.array(row['color'],dtype=float)
    match=(np.max(np.abs(crop[...,:3].astype(float)-colour),axis=-1)<48)&(crop[...,3]>160)
    if not match.any(): return result
    match=cv2.dilate(match.astype('uint8'),np.ones((3,3),np.uint8))
    if np.mean(crop[...,3]>250)>.95:
        crop[...,:3]=cv2.inpaint(crop[...,:3].copy(),match,3,cv2.INPAINT_TELEA)
    else:
        crop[...,3][match>0]=0
    return result


def vector_candidate(rgba, tolerance=2):
    """Convert whole flat layers only. Never interpret a soft shadow as a mask error."""
    alpha=rgba[...,3];core=alpha>=250
    if core.sum()<16 or core.sum()<.75*np.count_nonzero(alpha>16): return None
    pixels=rgba[core,:3].astype(float);colour=np.median(pixels,axis=0)
    if np.max(np.abs(pixels-colour))>tolerance:return None
    # A full opaque flat plane has exact canvas edges, not inset pixel-centre contours.
    if np.all(alpha==255):
        h,w=alpha.shape
        return {'shapes':[{'d':f'M0 0H{w}V{h}H0Z','operation':'combine'}],
            'color':[int(v) for v in colour],'stats':{'segments':4,'sourcePoints':4}}
    # Do not lose tiny isolated dots / one-pixel strokes in a contour fitter.
    _,labels,stats,_=cv2.connectedComponentsWithStats((alpha>=128).astype('uint8'))
    if any(s[cv2.CC_STAT_AREA]<4 for s in stats[1:]):return None
    mask=(alpha>=128).astype('uint8')
    shapes,stats=mask_to_paths(mask,tolerance=.45,smooth_pixels=.35,minimum_area=.15)
    if not shapes:return None
    return {'shapes':shapes,'color':[int(v) for v in colour],'stats':stats}


def safe_name(name):
    name=re.sub(r'[\x00-\x1f<>:"/\\|?*]','_',str(name)).strip(' .')[:90]
    if not name or name.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        raise ValueError('Invalid project name')
    return name
