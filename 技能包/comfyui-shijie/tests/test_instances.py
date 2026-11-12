import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from instances import duplicate_layers

class InstanceTests(unittest.TestCase):
 def test_reuse_keeps_original_and_places_independent_copy_by_alpha_box(self):
  source=np.zeros((50,80,4),np.uint8);source[10:20,20:30]=[60,100,180,255]
  images,names,report=duplicate_layers([source],['宝箱'],[{'source_index':0,'source_review':'PASS','name':'宝箱_第二处','x':40,'y':25}])
  self.assertEqual(names,['宝箱','宝箱_第二处']);np.testing.assert_array_equal(images[0],source)
  np.testing.assert_array_equal(images[1][25:35,40:50],source[10:20,20:30])
  images[1][25,40]=0;np.testing.assert_array_equal(images[0],source)
  self.assertEqual(report['generated_assets'],0)
 def test_unreviewed_source_cannot_be_mass_copied(self):
  im=np.ones((20,20,4),np.uint8)*255
  with self.assertRaises(ValueError):duplicate_layers([im],['源'],[{'source_index':0,'name':'复制','x':0,'y':0}])
 def test_instance_name_cannot_inject_an_extra_layer_name(self):
  im=np.ones((20,20,4),np.uint8)*255
  with self.assertRaises(ValueError):duplicate_layers([im],['源'],[{'source_index':0,'source_review':'PASS','name':'复制\n伪造层','x':0,'y':0}])
 def test_unicode_line_separators_cannot_inject_layer_names(self):
  im=np.ones((20,20,4),np.uint8)*255
  for separator in ('\u2028','\u2029','\x85'):
   with self.assertRaises(ValueError):duplicate_layers([im],['源'],[{'source_index':0,'source_review':'PASS','name':'复制'+separator+'伪造','x':0,'y':0}])
 def test_sparse_ink_does_not_vanish_when_downscaled(self):
  im=np.zeros((20,20,4),np.uint8);im[2,2]=[200,50,80,255];im[11,11]=[200,50,80,255]
  images,_,_=duplicate_layers([im],['源'],[{'source_index':0,'source_review':'PASS','name':'缩小','x':15,'y':15,'scale':.1}])
  self.assertGreater(int(images[1][15,15,3]),0)
 def test_outside_canvas_is_rejected_not_silently_clipped(self):
  im=np.zeros((20,20,4),np.uint8);im[4:10,4:10]=255
  with self.assertRaises(ValueError):duplicate_layers([im],['源'],[{'source_index':0,'source_review':'PASS','name':'复制','x':18,'y':18}])
 def test_uniform_scale_preserves_soft_alpha_and_colour(self):
  im=np.zeros((30,40,4),np.uint8);im[3:9,3:9]=[200,50,80,40]
  images,_,_=duplicate_layers([im],['阴影'],[{'source_index':0,'source_review':'PASS','name':'阴影复制','x':15,'y':10,'scale':2}])
  visible=images[1][...,3]>0
  self.assertTrue(visible.any());np.testing.assert_array_equal(images[1][visible,:3],np.tile([200,50,80],(visible.sum(),1)))

if __name__=='__main__':unittest.main()
