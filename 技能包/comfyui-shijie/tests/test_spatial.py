import unittest
import numpy as np
from spatial import compact_asset,validate_asset,materialize

class SpatialTests(unittest.TestCase):
 def test_tight_crop_preserves_pixel_bytes_and_origin(self):
  rgba=np.zeros((90,120,4),np.uint8);rgba[20:35,70:95]=[12,91,200,128]
  asset=compact_asset(dict(kind='bitmap',name='icon',rgba=rgba))
  self.assertEqual((asset['left'],asset['top']),(70,20));self.assertEqual(asset['rgba'].shape,(15,25,4))
  self.assertTrue(np.array_equal(materialize(asset,120,90),rgba))
 def test_transparent_hidden_rgb_does_not_expand_bounds(self):
  rgba=np.full((40,60,4),[30,90,120,0],np.uint8);rgba[10:12,14:16,3]=1
  asset=compact_asset(dict(kind='bitmap',name='shadow',rgba=rgba));self.assertEqual(asset['rgba'].shape,(2,2,4))
 def test_bad_placement_rejected(self):
  a=dict(kind='bitmap',name='bad',rgba=np.zeros((20,20,4),np.uint8),left=90,top=0)
  with self.assertRaises(ValueError):validate_asset(a,100,100)
 def test_real_vector_paths_remain_in_document_coordinates(self):
  rgba=np.zeros((40,60,4),np.uint8);rgba[10:20,20:30]=255;paths=[{'d':'M20 10H30V20H20Z','operation':'combine'}]
  a=compact_asset(dict(kind='shape',name='shape',rgba=rgba,shapes=paths,color=[255,255,255]))
  self.assertEqual(a['shapes'],paths);self.assertEqual(a['left'],20)

 def test_clear_hidden_rgb_without_mutating_source_or_visible_pixels(self):
  rgba=np.full((12,12,4),[210,30,70,255],np.uint8);rgba[4:8,4:8,3]=0
  old=rgba.copy();a=compact_asset(dict(kind='bitmap',name='frame',rgba=rgba))
  self.assertTrue(np.array_equal(rgba,old))
  self.assertTrue(np.all(a['rgba'][4:8,4:8,:3]==0))
  self.assertTrue(np.array_equal(a['rgba'][0],old[0]))
