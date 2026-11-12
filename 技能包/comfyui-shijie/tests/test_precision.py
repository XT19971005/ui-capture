import unittest
import numpy as np
from precision_pipeline import restore_panel,unmix,ordered,restore_background,precise_glyph,select_background

class PrecisionTests(unittest.TestCase):
 def test_source_pixel_panel_preserves_gradient_and_label_without_model_selection(self):
  rgb=np.arange(80*100*3,dtype=np.uint8).reshape(80,100,3)
  a=restore_panel(rgb,{'box':[5,5,95,75],'fill':[0,0,0],'radius':8,'source_pixels':True})
  self.assertTrue(np.array_equal(a[20:60,20:80,:3],rgb[20:60,20:80]))
  self.assertTrue(np.all(a[20:60,20:80,3]==255));self.assertEqual(a[0,0,3],0)

 def test_explicit_background_used_without_stretching(self):
  generated=np.full((20,30,4),255,np.uint8);external=np.full((20,30,4),[20,100,180,255],np.uint8)
  self.assertTrue(np.array_equal(select_background(generated,external),external))
  with self.assertRaises(ValueError):select_background(generated,external[:10])
 def test_transparent_background_not_silently_accepted(self):
  generated=np.full((20,30,4),255,np.uint8);external=generated.copy();external[1,1,3]=0
  with self.assertRaises(ValueError):select_background(generated,external)
 def test_rebuild_panel_has_no_source_text_hole(self):
  rgb=np.full((80,100,3),[70,180,220],np.uint8);rgb[30:50,40:60]=255
  a=restore_panel(rgb,{'box':[5,5,95,75],'fill':[70,180,220],'radius':8,'border':2,'border_color':[210,240,250],'inner_shadow':0})
  self.assertEqual(a[40,50,3],255);self.assertTrue(np.array_equal(a[40,50,:3],[70,180,220]));self.assertEqual(a[0,0,3],0)
 def test_soft_alpha_unmix_does_not_keep_blue_matte(self):
  bg=np.full((2,2,3),[20,100,180],float);fg=np.full((2,2,3),[240,210,10],float);alpha=np.full((2,2),.25)
  source=fg*alpha[...,None]+bg*(1-alpha[...,None]);out=unmix(source,bg,alpha)
  self.assertLessEqual(np.max(abs(out[...,:3].astype(float)-fg)),1);self.assertEqual(out[0,0,3],64)
 def test_explicit_layer_order_not_people_last(self):
  rows=[{'id':'front','z':9},{'id':'panel','z':5},{'id':'back','z':2}]
  self.assertEqual([r['id'] for r in ordered(rows)],['back','panel','front'])
 def test_duplicate_z_rejected(self):
  with self.assertRaises(ValueError):ordered([{'z':1},{'z':1}])
 def test_background_removes_foreground_without_rectangle_seam(self):
  yy,xx=np.mgrid[:120,:180];base=np.stack([30+xx*.1,90+yy*.2,180+yy*.1],axis=-1).astype(np.uint8)
  source=base.copy();source[25:90,40:140]=255;mask=np.zeros((120,180),np.uint8);mask[25:90,40:140]=255
  restored=restore_background(source,mask)
  self.assertLessEqual(np.max(abs(restored.astype(float)-base)),2)
  self.assertTrue(np.array_equal(restored[:5],base[:5]))
 def test_glyph_preserves_square_corners_and_antialias(self):
  mask=np.zeros((70,90),float);mask[10:60,20:70]=1
  rgba,shape=precise_glyph(mask,(0,0),(70,90))
  self.assertTrue(shape['shapes']);self.assertTrue(any('L' in s['d'] for s in shape['shapes']))
  self.assertTrue(np.any((rgba[...,3]>0)&(rgba[...,3]<255)))
