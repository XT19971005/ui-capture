import sys,json
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'依赖/PSD验证'))
from psd_tools import PSDImage
from PIL import Image,ImageChops,ImageStat
out=root/'自检记录/图像重建/当前验收';p=PSDImage.open(out/'真实图片重建.psd');im=p.composite(force=True);im.save(out/'PSD实际图层重绘.png');cached=p.topil().convert('RGBA');actual=im.convert('RGBA');mae=sum(ImageStat.Stat(ImageChops.difference(cached,actual)).mean)/4
counts={k:sum(l.kind==k for l in p.descendants()) for k in ['type','shape','pixel']}
assert counts['type']==25 and counts['shape']==76,counts
assert p[0].name=='画布底色'
assert mae<2,mae
result={'status':'PASS','independentRenderer':'psd-tools force=True','cachedVsRealLayerMAE':mae,'types':counts,'rootBottom':p[0].name}
(out/'PSD独立验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=True))
