"""Trace confirmed single-colour ink, including holes and brush contours."""
import io,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from PIL import Image
from runtime import ROOT
sys.path.insert(0,str(ROOT/'依赖/图像重建'))
def translate(d,tx,ty):
    tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',d);out=[];cmd=None;index=0
    for token in tokens:
        if token.isalpha():
            cmd=token;index=0
            if cmd not in ('M','L','C','Q','H','V','Z'):raise ValueError('Unsupported tracer path')
            out.append(cmd)
        else:
            value=float(token)+(ty if cmd=='V' or (cmd not in ('H',) and index%2) else tx);out.append(str(round(value,3)));index+=1
    return ' '.join(out)
def trace(alpha):
    import vtracer
    im=Image.fromarray(np.where(alpha>128,0,255).astype('uint8'));b=io.BytesIO();im.save(b,format='PNG')
    svg=vtracer.convert_raw_image_to_svg(b.getvalue(),img_format='png',colormode='binary',mode='spline',filter_speckle=1,length_threshold=3.5,corner_threshold=60,path_precision=3)
    paths=[]
    for p in ET.fromstring(svg).iter('{http://www.w3.org/2000/svg}path'):
        tr=re.search(r'translate\(([-\d.]+)[, ]+([-\d.]+)\)',p.get('transform',''));tx,ty=map(float,tr.groups()) if tr else (0,0)
        paths.append(translate(p.get('d',''),tx,ty))
    result=' '.join(p for p in paths if p.strip())
    if result or not np.any(alpha>128):return result
    # The spline tracer emits an empty path for a confirmed one-pixel mark.
    # Preserve that ink as exact grid rectangles; never publish an invalid d or
    # invent a larger contour. Merge matching runs across adjacent scanlines.
    rectangles=[];active={}
    for y,row in enumerate(alpha>128):
        padded=np.pad(row.astype(np.int8),(1,1));changes=np.diff(padded)
        runs=list(zip(np.flatnonzero(changes==1),np.flatnonzero(changes==-1)))
        next_active={}
        for left,right in runs:
            key=(int(left),int(right));next_active[key]=active.pop(key,y)
        for (left,right),top in active.items():rectangles.append((left,top,right,y))
        active=next_active
    for (left,right),top in active.items():rectangles.append((left,top,right,alpha.shape[0]))
    return ' '.join(f'M{x} {y}H{right}V{bottom}H{x}Z' for x,y,right,bottom in rectangles)
