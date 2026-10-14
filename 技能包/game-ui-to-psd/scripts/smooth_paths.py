"""Fit closed cubic Bezier paths to complete masks; preserve contour hierarchy."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '依赖/Python'))
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d

def unit(vector):
    length = np.linalg.norm(vector)
    return vector / length if length > 1e-12 else np.array([1., 0.])

def value(curve, t):
    t = np.asarray(t)[..., None]
    return (1-t)**3*curve[0]+3*(1-t)**2*t*curve[1]+3*(1-t)*t*t*curve[2]+t**3*curve[3]

def fit(points, tangent_start, tangent_end, tolerance, depth=0):
    if len(points) == 2:
        distance = np.linalg.norm(points[1]-points[0])/3
        return [np.array([points[0], points[0]+distance*tangent_start, points[1]+distance*tangent_end, points[1]])]
    chord = np.r_[0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    parameters = chord/chord[-1]
    def generate(t):
        b0=(1-t)**3; b1=3*t*(1-t)**2; b2=3*t*t*(1-t); b3=t**3
        matrix=np.stack([b1[:,None]*tangent_start,b2[:,None]*tangent_end],axis=2).reshape(-1,2)
        residual=(points-(b0+b1)[:,None]*points[0]-(b2+b3)[:,None]*points[-1]).reshape(-1)
        alpha=np.linalg.lstsq(matrix,residual,rcond=None)[0]
        distance=np.linalg.norm(points[-1]-points[0])
        if np.any(alpha <= 1e-6*distance) or np.any(alpha > 4*chord[-1]): alpha=np.array([distance/3,distance/3])
        return np.array([points[0],points[0]+alpha[0]*tangent_start,points[-1]+alpha[1]*tangent_end,points[-1]])
    curve=generate(parameters)
    for iteration in range(5):
        delta=value(curve,parameters)-points; errors=np.einsum('ij,ij->i',delta,delta)
        split=int(np.argmax(errors)); maximum=float(errors[split])
        if maximum <= tolerance*tolerance: return [curve]
        if iteration == 4 or maximum > 9*tolerance*tolerance: break
        t=parameters[:,None]; derivative=3*((1-t)**2*(curve[1]-curve[0])+2*(1-t)*t*(curve[2]-curve[1])+t*t*(curve[3]-curve[2]))
        second=6*((1-t)*(curve[2]-2*curve[1]+curve[0])+t*(curve[3]-2*curve[2]+curve[1]))
        numerator=np.einsum('ij,ij->i',delta,derivative)
        denominator=np.einsum('ij,ij->i',derivative,derivative)+np.einsum('ij,ij->i',delta,second)
        updated=np.clip(parameters-np.divide(numerator,denominator,out=np.zeros_like(numerator),where=np.abs(denominator)>1e-10),0,1)
        if np.any(np.diff(updated)<=0): break
        parameters=updated;curve=generate(parameters)
    split=max(1,min(len(points)-2,split))
    if depth > 40: split=len(points)//2
    center=unit(points[split-1]-points[split+1])
    return fit(points[:split+1],tangent_start,center,tolerance,depth+1)+fit(points[split:],-center,tangent_end,tolerance,depth+1)

def mask_to_paths(mask, origin=(0,0), pixel_size=1., tolerance=.45, smooth_pixels=.5, minimum_area=.15, preserve_corners=False):
    contours,hierarchy=cv2.findContours(mask.astype('uint8'),cv2.RETR_TREE,cv2.CHAIN_APPROX_NONE)
    if hierarchy is None: return [], {'segments':0,'sourcePoints':0}
    def depth(index):
        count=0
        while hierarchy[0,index,3]>=0:index=int(hierarchy[0,index,3]);count+=1
        return count
    shapes=[];segments=0;source_points=0
    for index in sorted(range(len(contours)),key=depth):
        contour=contours[index]
        if cv2.contourArea(contour)*pixel_size**2<minimum_area:continue
        points=(contour.reshape(-1,2).astype(float)+.5)*pixel_size+np.array(origin)
        if len(points)<4:continue
        source_points+=len(points)
        if preserve_corners:
            # Do not fit one smooth spline through square font corners or long
            # straight strokes. Simplify JPEG stair steps, preserve sharp joins,
            # and fit only the genuinely curved spans between those joins.
            poly=(cv2.approxPolyDP(contour,max(.6,tolerance)/pixel_size,True).reshape(-1,2).astype(float)+.5)*pixel_size+np.array(origin)
            for j in range(len(poly)):
                k=(j+1)%len(poly);dx,dy=poly[k]-poly[j]
                if abs(dx)>8 and abs(dy)<=1.5:poly[j,1]=poly[k,1]=(poly[j,1]+poly[k,1])/2
                if abs(dy)>8 and abs(dx)<=1.5:poly[j,0]=poly[k,0]=(poly[j,0]+poly[k,0])/2
            sharp=[]
            for j,p in enumerate(poly):
                before=p-poly[j-1];after=poly[(j+1)%len(poly)]-p
                turn=np.degrees(np.arccos(np.clip(np.dot(unit(before),unit(after)),-1,1)))
                axis_straight=any(np.linalg.norm(v)>25 and min(abs(v[0]),abs(v[1]))<1.5 for v in (before,after))
                sharp.append(turn>=60 or axis_straight)
            start=next((j for j,v in enumerate(sharp) if v),0);rotated=np.roll(poly,-start,axis=0);sharp=sharp[start:]+sharp[:start]
            pair=lambda p:f'{p[0]:.4f} {p[1]:.4f}'
            first=rotated[0] if sharp[0] else (rotated[-1]+rotated[0])/2
            parts=[]
            for j in range(1,len(poly)+1):
                k=j%len(poly);p=rotated[k]
                if sharp[k]:parts.append('L'+pair(p))
                else:parts.append('L'+pair((rotated[k-1]+p)/2)+'Q'+pair(p)+' '+pair((p+rotated[(k+1)%len(poly)])/2))
            shapes.append({'d':'M'+pair(first)+''.join(parts)+'Z','operation':'subtract' if depth(index)%2 else 'combine'})
            segments+=len(parts)
            continue
        smoothing=smooth_pixels(cv2.contourArea(contour)*pixel_size**2) if callable(smooth_pixels) else smooth_pixels
        if smoothing:points=gaussian_filter1d(points,smoothing/pixel_size,axis=0,mode='wrap')
        # Two open halves avoid a zero-length endpoint chord for the closed outline.
        middle=len(points)//2;closed=np.vstack([points,points[0]])
        t0=unit(points[1]-points[-1]);tm=unit(points[(middle+1)%len(points)]-points[middle-1])
        curves=fit(closed[:middle+1],t0,-tm,tolerance)+fit(closed[middle:],tm,-t0,tolerance)
        def pair(point):return f'{point[0]:.4f} {point[1]:.4f}'
        path='M'+pair(curves[0][0])+''.join('C'+pair(c[1])+' '+pair(c[2])+' '+pair(c[3]) for c in curves)+'Z'
        shapes.append({'d':path,'operation':'subtract' if depth(index)%2 else 'combine'})
        segments+=len(curves)
    return shapes, {'segments':segments,'sourcePoints':source_points}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--regions',required=True);parser.add_argument('--output',default='03_结构/平滑矢量.json')
    args=parser.parse_args();root=Path(args.project).resolve();DIRS=__import__('project_dirs').project_dirs(root);job=json.loads((root/(DIRS['plan']+'/项目.json')).read_text('utf8'))
    source=np.array(Image.open(root/job['source']).convert('RGB')).astype('int16');regions=json.loads(Path(args.regions).read_text('utf8'));rows=[]
    for region in regions:
        x,y,right,bottom=region['box'];v=source[y:bottom,x:right];R,G,B=v[:,:,0],v[:,:,1],v[:,:,2]
        if region.get('mode')=='brown':mask=(R<185)&(G<85)&(B<75)
        elif region.get('mode')=='cream':mask=(R>190)&(G>165)&(B>100)
        elif region.get('mode')=='white':mask=(R>188)&(G>175)&(B>168)
        else:
            mask=np.ones(v.shape[:2],bool)
            for channel,key in enumerate(['r','g','b']):
                lower,upper=region['rules'].get(key,[0,255]);mask&=(v[:,:,channel]>=lower)&(v[:,:,channel]<=upper)
        shapes,stats=mask_to_paths(mask,(x,y),tolerance=region.get('tolerance',.45),smooth_pixels=region.get('smoothPixels',.65),minimum_area=region.get('minimumArea',.2),preserve_corners=region.get('preserveCorners',False))
        if not shapes:raise ValueError('没有识别到完整轮廓：'+region['name'])
        integrity={'box':region['box'],'minIoU':region.get('minIoU',.9)}
        if 'rules' in region:integrity['rules']=region['rules']
        else:integrity['mode']=region['mode']
        rows.append({'kind':'shape','name':region['name'],'color':region['color'],'shapes':shapes,'smoothing':{**stats,'visualReview':'REQUIRED'},'integrityRegion':integrity})
    destination=root/(args.output.replace('03_结构/',DIRS['plan']+'/',1) if args.output.startswith('03_结构/') else args.output);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({'file':str(destination),'shapes':len(rows)},ensure_ascii=False))

if __name__=='__main__':main()

