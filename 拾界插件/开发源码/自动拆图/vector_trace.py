"""Trace confirmed single-colour ink, including holes and brush contours."""
import io,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
import cv2,numpy as np
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
    ink=np.asarray(alpha)>128
    if not np.any(ink):return ''
    # VTracer's spline simplification can emit an empty/zero-area path for a
    # tiny component or counter, even while its other contours are valid. Keep
    # these independently, before tracing; testing only whether the whole SVG
    # is empty loses dots and fills holes in otherwise successful logos.
    tracing=ink.copy();small=[];outlined=set();ink_labels=None
    for foreground,connectivity in ((True,8),(False,4)):
        count,labels,stats,_=cv2.connectedComponentsWithStats(
            (ink if foreground else ~ink).astype('uint8'),connectivity=connectivity)
        if foreground:ink_labels=labels
        for label in range(1,count):
            x,y,w,h,area=map(int,stats[label])
            if area>4:
                if not foreground:continue
                region=labels[y:y+h,x:x+w]==label
                if np.any(cv2.erode(region.astype('uint8'),np.ones((3,3),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0)):continue
                # A nonempty spline can still consist solely of zero-area
                # lines. Only replace a confirmed thin component that exhibits
                # this failure, never a good smooth main silhouette.
                candidate=spline(region)
                if candidate and not any(degenerate(p) for p in candidate):continue
                small.append(translate(grid_outline(region),x,y));outlined.add(label)
                tracing[y:y+h,x:x+w][region]=False
                continue
            # Background connected to the canvas edge is not a counter.
            if not foreground and (x==0 or y==0 or x+w==ink.shape[1] or y+h==ink.shape[0]):continue
            if not foreground and outlined.intersection(np.unique(ink_labels[max(0,y-1):y+h+1,max(0,x-1):x+w+1])):continue
            region=labels[y:y+h,x:x+w]==label
            tracing[y:y+h,x:x+w][region]=not foreground
            small.append(translate(rectangles(region),x,y))
    result=' '.join(p for p in [*spline(tracing),*small] if p.strip())
    if result:return result
    return rectangles(ink)

def spline(ink):
    import vtracer
    if not np.any(ink):return []
    im=Image.fromarray(np.where(ink,0,255).astype('uint8'));b=io.BytesIO();im.save(b,format='PNG')
    svg=vtracer.convert_raw_image_to_svg(b.getvalue(),img_format='png',colormode='binary',mode='spline',filter_speckle=1,length_threshold=3.5,corner_threshold=60,path_precision=3)
    paths=[]
    for p in ET.fromstring(svg).iter('{http://www.w3.org/2000/svg}path'):
        tr=re.search(r'translate\(([-\d.]+)[, ]+([-\d.]+)\)',p.get('transform',''));tx,ty=map(float,tr.groups()) if tr else (0,0)
        paths.append(translate(p.get('d',''),tx,ty))
    return paths

def degenerate(d):
    """The tracer emits M/C/Z; collinear control points enclose no ink."""
    if not d.strip():return True
    for part in re.split(r'(?=M)',d):
        if not part.strip():continue
        numbers=re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',part)
        points=np.array(numbers,dtype=np.float32).reshape(-1,2)
        if len(points)<3 or cv2.contourArea(cv2.convexHull(points))<.0001:return True
    return False

def grid_outline(ink):
    """Walk exposed cell edges, merging a connected strip into its boundary.

    Keep real one-pixel stair steps rather than thickening them into a fitted
    stroke. This bounded exception produces contours, not per-pixel rectangles.
    Normal smooth marks continue through the spline tracer.
    """
    limit=4096
    failure='纯色细线轮廓过于复杂，需要校对；未发布可能缺失笔画的矢量'
    if np.count_nonzero(ink)>limit:raise ValueError(failure)
    edges={};height,width=ink.shape
    def edge(start,end,direction):edges.setdefault(start,[]).append((end,direction))
    for y,x in zip(*np.where(ink)):
        x,y=int(x),int(y)
        if y==0 or not ink[y-1,x]:edge((x,y),(x+1,y),0)
        if x==width-1 or not ink[y,x+1]:edge((x+1,y),(x+1,y+1),1)
        if y==height-1 or not ink[y+1,x]:edge((x+1,y+1),(x,y+1),2)
        if x==0 or not ink[y,x-1]:edge((x,y+1),(x,y),3)
    contours=[];vertices=0
    while edges:
        start=next(iter(edges));point=start;direction=0;points=[]
        while True:
            points.append(point);choices=edges[point]
            # At diagonal contacts, turn left to keep 8-connected foreground
            # in one boundary instead of creating a rectangle for every cell.
            index=min(range(len(choices)),key=lambda i:(choices[i][1]-direction+1)%4)
            point,direction=choices.pop(index)
            if not choices:del edges[points[-1]]
            if point==start:break
        points=cv2.approxPolyDP(np.array(points,dtype=np.float32),0,True).reshape(-1,2)
        vertices+=len(points)
        if vertices>limit:raise ValueError(failure)
        contours.append('M'+'L'.join(f'{int(x)} {int(y)}' for x,y in points)+'Z')
    return ' '.join(contours)

def rectangles(ink):
    """Exact compact grid runs for confirmed tiny ink, never an enlarged mark."""
    rectangles=[];active={}
    for y,row in enumerate(ink):
        padded=np.pad(row.astype(np.int8),(1,1));changes=np.diff(padded)
        runs=list(zip(np.flatnonzero(changes==1),np.flatnonzero(changes==-1)))
        next_active={}
        for left,right in runs:
            key=(int(left),int(right));next_active[key]=active.pop(key,y)
        for (left,right),top in active.items():rectangles.append((left,top,right,y))
        active=next_active
    for (left,right),top in active.items():rectangles.append((left,top,right,ink.shape[0]))
    return ' '.join(f'M{x} {y}H{right}V{bottom}H{x}Z' for x,y,right,bottom in rectangles)
