"""Counterexamples collected in the complete standards audit; no model calls."""
import unittest
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from engine import segment,flat_ink_parts,text_nodes

def row(text,box):
 x,y,r,b=box;return {'id':'t','text':text,'confidence':1,'bbox':box,'quad':[[x,y],[r,y],[r,b],[x,b]]}

class ImageStandardsTests(unittest.TestCase):
 def test_same_box_colour_logo_entries_keep_complete_ink(self):
  rgb=np.full((100,150,3),[250,200,150],np.uint8);rgb[20:75,30:70]=[190,20,30];rgb[20:75,70:110]=[20,40,180]
  a={'id':'red','name':'红色','kind':'logo','box':[15,10,125,85]};b={**a,'id':'blue','name':'蓝色'}
  rows=segment(rgb,[a,b],lambda *_:None,lambda:False)
  self.assertEqual(sum(np.count_nonzero(r['mask']) for r in rows),4400)
  self.assertEqual(len(rows),2)

 def test_small_disconnected_blue_stroke_keeps_its_colour(self):
  ink=np.zeros((80,180),np.uint8);ink[10:65,10:80]=255;ink[20:23,120:122]=255
  patch=np.full((80,180,3),255,np.uint8);patch[10:65,10:80]=[180,10,20];patch[20:23,120:122]=[20,30,180]
  parts=flat_ink_parts(patch,ink)
  dot=[c for p,c in parts if np.any(p[20:23,120:122])]
  self.assertEqual(len(dot),1);self.assertLess(np.linalg.norm(dot[0]-[20,30,180]),2)

 def gradient_nodes(self,text,width,angle):
  mask=Image.new('L',(width,80));font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',48)
  ImageDraw.Draw(mask).text((6,0),text,font=font,fill=255);yy,xx=np.indices((80,width));v=yy/80 if angle==90 else xx/width
  colours=np.stack([230-120*v,np.full_like(v,30),40+120*v],axis=2).astype('uint8');rgb=np.full((80,width,3),255,np.uint8);ink=np.array(mask)>180;rgb[ink]=colours[ink]
  return text_nodes([row(text,[0,0,width,80])],rgb,set())[0]

 def test_vertical_gradient_is_not_replaced_with_single_colour(self):
  nodes=self.gradient_nodes('TEST TEST',330,90)
  self.assertIn('gradient',nodes[0]);self.assertAlmostEqual(abs(nodes[0]['gradient']['angle']),90,delta=5)

 def test_narrow_horizontal_gradient_is_preserved(self):
  nodes=self.gradient_nodes('A',60,0)
  self.assertIn('gradient',nodes[0]);self.assertAlmostEqual(nodes[0]['gradient']['angle'],0,delta=5)

 def test_vertical_chinese_fits_glyphs_then_keeps_one_editable_phrase(self):
  font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',40);im=Image.new('RGB',(80,160),'white');d=ImageDraw.Draw(im)
  for i,ch in enumerate('中文'):d.text((20,10+i*70),ch,font=font,fill='#334466')
  from unittest.mock import patch
  import text_style
  with patch('text_style.estimate',wraps=text_style.estimate) as fit:
   nodes,_=text_nodes([row('中文',[10,5,70,155])],np.array(im),set())
  self.assertEqual([call.args[1] for call in fit.call_args_list],['中','文'])
  self.assertTrue(all(call.args[0].shape[:2]==(75,60) for call in fit.call_args_list))
  self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],'中\n文');self.assertEqual(nodes[0]['lineHeight'],75)
  self.assertEqual(nodes[0]['sourceBox'],{'x0':10,'y0':5,'x1':70,'y1':155})
  for n in nodes:self.assertAlmostEqual(n['fontSize'],40,delta=3);self.assertEqual(n['fontWeight'],400)

if __name__=='__main__':unittest.main()
