"""Read-only color-region analysis into native vector descriptions; never subtract actor alpha."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'依赖/Python'))
import cv2,numpy as np
from PIL import Image
ap=argparse.ArgumentParser();ap.add_argument('--project',required=True);ap.add_argument('--regions',required=True);a=ap.parse_args()
root=Path(a.project).resolve();DIRS=__import__('project_dirs').project_dirs(root);job=json.loads((root/(DIRS['plan']+'/项目.json')).read_text('utf8'));src=np.array(Image.open(root/job['source']).convert('RGB'))
regions=json.loads(Path(a.regions).read_text('utf8'));out=[]
for region in regions:
 x,y,right,bottom=region['box'];v=src[y:bottom,x:right].astype('int16');R,G,B=v[:,:,0],v[:,:,1],v[:,:,2];mode=region.get('mode')
 if 'rules' in region:
  mask=np.ones(v.shape[:2],bool)
  for k,key in enumerate(['r','g','b']):
   low,high=region['rules'].get(key,[0,255]);mask&=(v[:,:,k]>=low)&(v[:,:,k]<=high)
 elif mode=='brown':mask=(R<185)&(G<85)&(B<75)
 elif mode=='cream':mask=(R>190)&(G>165)&(B>100)
 elif mode=='white':mask=(R>188)&(G>175)&(B>168)
 else:raise ValueError('每个 region 指定 mode 或 RGB rules；不能猜测颜色')
 if region.get('keepLargest'):
  n,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype('uint8'));ids=sorted(range(1,n),key=lambda i:int(stats[i,4]),reverse=True)[:region['keepLargest']]
  if len(ids)!=region['keepLargest']:raise ValueError('完整形状数不足: '+region['name'])
  mask=np.isin(labels,ids)
 scale=region.get('pixelScale',4);grid=np.repeat(np.repeat(mask,scale,axis=0),scale,axis=1).astype('uint8');cs,h=cv2.findContours(grid,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
 def depth(i):
  d=0
  while h[0,i,3]>=0:i=int(h[0,i,3]);d+=1
  return d
 parts=[]
 for i in sorted(range(len(cs)),key=depth):
  if cv2.contourArea(cs[i])<1:continue
  pts=cv2.approxPolyDP(cs[i],region.get('epsilon',.35)*scale,True).reshape(-1,2)
  if len(pts)<3:continue
  parts.append({'d':'M'+'L'.join(f'{(p+.5)/scale+x:g} {(q+.5)/scale+y:g}' for p,q in pts)+'Z','operation':'subtract' if depth(i)%2 else 'combine'})
 if not parts:raise ValueError('空矢量形状: '+region['name'])
 integrity={'box':region['box'],'minIoU':region.get('minIoU',.9)}
 if 'rules' in region:integrity['rules']=region['rules']
 else:integrity['mode']=mode
 out.append({'kind':'shape','name':region['name'],'color':region['color'],'shapes':parts,'integrityRegion':integrity,'analysis':{'box':region['box'],'sourceColorPixels':int(mask.sum()),'completionReview':'REQUIRED'}})
dest=root/(DIRS['plan']+'/矢量分析.json');dest.write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf8');print(json.dumps({'file':str(dest),'shapeCount':len(out),'visualReview':'REQUIRED'},ensure_ascii=False))
