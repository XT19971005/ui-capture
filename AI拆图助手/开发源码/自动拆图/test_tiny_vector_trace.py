import unittest,numpy as np
from vector_trace import trace
from design_properties import mask
class TinyInkTests(unittest.TestCase):
 def test_one_pixel_does_not_publish_empty_native_path(self):
  a=np.zeros((5,5),dtype=np.uint8);a[2,2]=255
  d=trace(a)
  self.assertTrue(d.strip(),'real tracer returns an empty d for one-pixel confirmed ink')
  mask({'type':'path','enabled':True,'x':0,'y':0,'width':5,'height':5,'d':d})
 def test_thin_confirmed_stroke_not_lost(self):
  a=np.zeros((12,12),dtype=np.uint8);a[3:9,4]=255
  self.assertTrue(trace(a).strip())
 def test_no_ink_remains_empty(self):
  self.assertEqual(trace(np.zeros((5,5),dtype=np.uint8)),'')
if __name__=='__main__':unittest.main()
