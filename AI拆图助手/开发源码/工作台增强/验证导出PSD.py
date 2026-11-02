import sys,json
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'依赖/PSD验证'))
from psd_tools import PSDImage
from PIL import Image,ImageChops,ImageStat
out=root/'自检记录/便捷操作';results=[]
for name in ['网页所选','图片所选']:
 p=PSDImage.open(out/(name+'.psd'));actual=p.composite(force=True).convert('RGBA');cached=p.topil().convert('RGBA');# Ignore undefined RGB under alpha=0; compare compositing on black and white, and alpha itself.
 diffs=[]
 for value in [0,255]:
  bg=Image.new('RGBA',p.size,(value,value,value,255));diffs.append(sum(ImageStat.Stat(ImageChops.difference(Image.alpha_composite(bg,cached),Image.alpha_composite(bg,actual))).mean)/4)
 alpha=sum(ImageStat.Stat(ImageChops.difference(cached.getchannel('A'),actual.getchannel('A'))).mean)
 mae=max(*diffs,alpha)
 counts={k:sum(l.kind==k for l in p.descendants()) for k in ['type','shape','pixel','group']}
 assert counts['type']>0 and counts['shape']>=2,counts
 assert mae<3,(name,mae)
 actual.save(out/(name+'_实际图层重绘.png'));results.append({'file':name+'.psd','layerTypes':counts,'cachedVsRealMAE':mae})
(out/'PSD独立重绘验收.json').write_text(json.dumps({'status':'PASS','renderer':'psd-tools force=True','results':results},ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(results,ensure_ascii=True))
