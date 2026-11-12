import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit import compare_rgba,check_required_texts

class AuditTests(unittest.TestCase):
 def test_transparent_hidden_rgb_does_not_fail_visible_check(self):
  a=np.zeros((3,4,4),np.uint8);b=a.copy();b[0,0,:3]=255
  r=compare_rgba(a,b)
  self.assertFalse(r['raw_equal']);self.assertTrue(r['visible_equal'])
 def test_black_cache_with_colour_layers_fails(self):
  a=np.zeros((3,4,4),np.uint8);a[...,3]=255;b=a.copy();b[...,:3]=[80,200,220]
  r=compare_rgba(a,b)
  self.assertFalse(r['visible_equal']);self.assertGreater(r['visible_mean_absolute_error'],100)
 def test_spaces_are_significant_and_missing_duplicate_is_counted(self):
  r=check_required_texts(['Auspicious year','2024','2024'],['Auspiciousyear','2024'])
  self.assertEqual(r['missing'],['Auspicious year','2024'])
  self.assertEqual(r['unexpected'],['Auspiciousyear'])

if __name__=='__main__':unittest.main()
