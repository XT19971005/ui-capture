"""Counterexamples for multiline fallback geometry and subtly varied materials."""
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import engine,text_style

def row(text,box):
 x,y,r,b=box
 return {'id':'text','text':text,'bbox':list(box),'quad':[[x,y],[r,y],[r,b],[x,b]],'confidence':1}

class TextGeometry(unittest.TestCase):
 def test_unmatched_multiline_measures_longest_line_and_keeps_source_top_left(self):
  rgb=np.full((80,100,3),240,np.uint8)
  with patch('text_style.estimate',return_value=None):
   nodes,_=engine.text_nodes([row('SUMMER\nOPEN\nDAILY',(12,14,58,51))],rgb,set())
  n=nodes[0]
  self.assertGreaterEqual(n['fontSize'],9)
  self.assertEqual((n['x'],n['y']),(12,14),'failed fit must not invent centering offsets')
  self.assertAlmostEqual(n['lineHeight'],37/3)
  self.assertFalse(n.get('fitWidth',False));self.assertTrue(n['fontMatchApproximate'])
  self.assertTrue(n['review'])

 def test_unmatched_single_line_does_not_recenter_a_padded_source_box(self):
  rgb=np.full((60,160,3),240,np.uint8)
  with patch('text_style.estimate',return_value=None):
   nodes,_=engine.text_nodes([row('NOTE',(20,10,140,30))],rgb,set())
  self.assertEqual((nodes[0]['x'],nodes[0]['y']),(20,10))
  self.assertEqual(nodes[0]['sourceBox'],{'x0':20,'y0':10,'x1':140,'y1':30})

 def test_nearby_background_colors_are_one_material_for_native_multiline_fitting(self):
  width,height=130,96;yy,xx=np.mgrid[:height,:width]
  rgb=np.stack([25+xx*.4,30+yy*.3,50+(xx+yy)*.2],axis=2).astype('uint8')
  image=Image.fromarray(rgb);draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
  text='WEEKEND\nOPEN\nDAILY'
  for i,line in enumerate(text.split('\n')):draw.text((7,6+i*22),line,font=font,fill='#e8dfc4')
  pixels=np.array(image);buckets=(pixels.reshape(-1,3)//16)*16
  _,counts=np.unique(buckets,axis=0,return_counts=True)
  self.assertLess(max(counts)/len(buckets),.2,'fixture must defeat a single quantized-bucket material threshold')
  fitted=text_style.estimate(pixels,text)
  self.assertIsNotNone(fitted)
  self.assertAlmostEqual(fitted['fontSize'],16,delta=2)
  self.assertAlmostEqual(fitted['lineHeight'],22,delta=1)
  self.assertLess(fitted['offsetY'],13)
  self.assertFalse(fitted['fitWidth'])

if __name__=='__main__':unittest.main()
