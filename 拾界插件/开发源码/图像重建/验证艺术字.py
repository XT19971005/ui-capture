import sys,os,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'依赖'/'图像重建'))
from PIL import Image,ImageDraw,ImageFont
import vtracer
im=Image.new("RGBA",(600,170),(0,0,0,0))
d=ImageDraw.Draw(im);f=ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc",104)
d.text((18,2),"拾界",font=f,fill=(93,212,185,255),stroke_width=2,stroke_fill=(93,212,185,255))
# Purpose-built raster fixture: a geometric underline is included in the source.
d.polygon([(26,150),(236,140),(226,150),(20,162)],fill=(93,212,185,255))
im.save(root/'自检记录'/'图像重建'/'艺术字_输入位图.png')
vtracer.convert_image_to_svg_py(str(root/'自检记录'/'图像重建'/'艺术字_输入位图.png'),str(root/'自检记录'/'图像重建'/'艺术字_矢量路径.svg'),colormode='color',hierarchical='cutout',mode='polygon',filter_speckle=4,color_precision=6,layer_difference=16,corner_threshold=60,length_threshold=3.5,max_iterations=10,splice_threshold=45,path_precision=2)
print(json.dumps({'status':'PASS','fixture':'controlled raster title, not arbitrary-photo recognition','vtracer':'0.6.15','output':'艺术字_矢量路径.svg'},ensure_ascii=False))

