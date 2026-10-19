import unittest
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from text_style import estimate

class TextStyleTests(unittest.TestCase):
 def test_real_glyph_pixels_choose_regular_italic_instead_of_default_bold(self):
  font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',46);text='河南文物保护';box=font.getbbox(text)
  glyph=Image.new('L',(box[2]-box[0]+12,box[3]-box[1]+8));ImageDraw.Draw(glyph).text((6-box[0],4-box[1]),text,font=font,fill=255)
  h=glyph.height;italic=glyph.transform((glyph.width+int(h*.22)+2,h),Image.Transform.AFFINE,(1,.22,-.22*h,0,1,0),resample=Image.Resampling.BICUBIC)
  image=Image.new('RGB',(italic.width+12,italic.height+12),'white');image.paste((190,120,110),(6,6,6+italic.width,6+italic.height),italic)
  result=estimate(np.array(image),text)
  self.assertEqual(result['fontStyle'],'italic');self.assertEqual(result['fontWeight'],400)
  self.assertFalse(result['fitWidth']);self.assertLess(result['glyphHeight'],50)
 def test_observed_slant_is_preserved_when_font_family_only_approximates_source(self):
  from runtime import ROOT
  project=ROOT.parent/'交付包/河南文物公益行动'
  if not project.is_dir():self.skipTest('local real-image fixture unavailable')
  rows=json.loads((project/'1_过程/02_结构/OCR.json').read_text('utf8'));row=next(r for r in rows if '应急' in r['text'])
  im=np.array(Image.open(next((project/'2_输出').glob('*_原图.jpg'))).convert('RGB'));x,y,right,bottom=row['bbox']
  result=estimate(im[y:bottom,x:right],row['text'])
  self.assertEqual(result['fontStyle'],'italic');self.assertGreater(result['textSkew'],.08);self.assertLess(result['textSkew'],.25)

if __name__=='__main__':unittest.main()
