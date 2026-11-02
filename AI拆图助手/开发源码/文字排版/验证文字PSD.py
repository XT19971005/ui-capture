import sys,json
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'依赖/PSD验证'))
from psd_tools import PSDImage
from PIL import Image,ImageChops,ImageStat
out=root/'自检记录/文字排版';p=PSDImage.open(out/'文字格式.psd')
types=[l for l in p.descendants() if l.kind=='type']
assert len(types)==30,len(types)
assert sum(l.text=='Today' for l in types)==2
assert any(l.text=='4.' for l in types) and any(l.text=='5.' for l in types)
actual=p.composite(force=True).convert('RGBA');cached=p.topil().convert('RGBA');maes=[]
for value in [0,255]:
 bg=Image.new('RGBA',p.size,(value,value,value,255));maes.append(sum(ImageStat.Stat(ImageChops.difference(Image.alpha_composite(bg,cached),Image.alpha_composite(bg,actual))).mean)/4)
assert max(maes)<3,maes
actual.save(out/'文字PSD_实际图层合成.png')
(out/'文字PSD回读验收.json').write_text(json.dumps({'status':'PASS','editableTextLayers':len(types),'compositeMAE':max(maes),'textContents':[l.text for l in types],'note':'Native records and stored layer composite verified. Photoshop client text editing not automated.'},ensure_ascii=False,indent=2),encoding='utf8')
print('PASS native PSD: 30 editable text records and independent layer composite; MAE',max(maes))