"""Read-only PSD audit. Structural checks never grant visual acceptance.

Run with an environment already containing psd-tools, Pillow and NumPy.
No models, network access, rendered sheets or changes to source assets.
"""
import argparse,json
from collections import Counter
from pathlib import Path
import numpy as np
from PIL import Image

def compare_rgba(first,second):
 a=np.asarray(first,dtype=np.uint8);b=np.asarray(second,dtype=np.uint8)
 if a.shape!=b.shape:return {'raw_equal':False,'visible_equal':False,'shape_mismatch':True}
 def visible(value):
  alpha=value[...,3:4].astype(float)/255
  return np.concatenate([value[...,:3]*alpha,value[...,3:4]],axis=-1)
 delta=abs(visible(a)-visible(b))
 return {'raw_equal':bool(np.array_equal(a,b)),'visible_equal':bool(not np.any(delta)),
         'visible_mean_absolute_error':float(delta.mean()),'visible_max_error':float(delta.max())}

def check_required_texts(required,actual):
 # Only PSD line-ending convention is normalized; punctuation and spaces matter.
 norm=lambda text:text.replace('\r\n','\n').replace('\r','\n')
 expected=Counter(map(norm,required));found=Counter(map(norm,actual))
 return {'missing':list((expected-found).elements()),'unexpected':list((found-expected).elements())}

def inspect(psd_path,required_texts=(),minimum_shapes=0):
 from psd_tools import PSDImage
 psd_path=Path(psd_path);p=PSDImage.open(psd_path)
 leaves=[layer for layer in p.descendants() if not layer.is_group()]
 texts=[layer.text for layer in leaves if layer.kind=='type']
 rows=[];issues=[]
 for index,layer in enumerate(leaves,1):
  matches=list(psd_path.parent.glob(f'{index:02d}_*.png'))
  row={'index':index,'name':layer.name,'kind':layer.kind,'visible':layer.visible,
       'bbox':list(layer.bbox),'png_match_count':len(matches)}
  if len(matches)==1:
   png=Image.open(matches[0]).convert('RGBA');raster=layer.topil()
   if raster is None:issues.append(f'{index:02d} missing layer raster')
   else:
    canvas=Image.new('RGBA',p.size);canvas.paste(raster.convert('RGBA'),(layer.left,layer.top))
    row['png_vs_psd']=compare_rgba(png,canvas)
    if not row['png_vs_psd']['visible_equal']:issues.append(f'{index:02d} PNG differs from PSD')
  else:issues.append(f'{index:02d} expected exactly one numbered PNG')
  rows.append(row)
 cache=p.topil();forced=p.composite(force=True)
 preview=compare_rgba(cache.convert('RGBA'),forced.convert('RGBA')) if cache and forced else {'visible_equal':False}
 # Independent PSD compositors round alpha/blending differently at 8-bit depth.
 preview['within_rounding_tolerance']=bool(preview.get('visible_max_error',float('inf'))<=3 and preview.get('visible_mean_absolute_error',float('inf'))<=.5)
 if not preview['within_rounding_tolerance']:issues.append('cached composite differs from independently recomposited layers beyond rounding tolerance')
 text_check=check_required_texts(required_texts,texts)
 if text_check['missing']:issues.append('required editable text missing')
 shapes=sum(layer.kind=='shape' for layer in leaves)
 if shapes<minimum_shapes:issues.append('required native vector shape count not met')
 return {'file':str(psd_path.resolve()),'canvas':list(p.size),'layer_count':len(leaves),
         'native_texts':texts,'native_shape_count':shapes,'required_text_check':text_check,
         'layers':rows,'composite_check':preview,'issues':issues,
         'structure_status':'FAIL' if issues else 'PASS',
         'visual_status':'NOT_CHECKED','final_acceptance':'NOT_GRANTED'}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('psd');parser.add_argument('--requirements',type=Path);parser.add_argument('--output',required=True,type=Path)
 args=parser.parse_args();requirements=json.loads(args.requirements.read_text(encoding='utf8')) if args.requirements else {}
 report=inspect(args.psd,requirements.get('editable_texts',[]),requirements.get('minimum_native_shapes',0))
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({k:report[k] for k in ('layer_count','native_shape_count','issues','structure_status','visual_status')},ensure_ascii=False))

if __name__=='__main__':main()
