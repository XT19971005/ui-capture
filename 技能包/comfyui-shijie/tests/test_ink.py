import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import estimate_ink

class InkTests(unittest.TestCase):
 def test_white_button_letters_are_not_their_dark_drop_shadow(self):
  im=np.full((40,100,3),[125,150,210],np.uint8)
  im[12:34,18:29]=[10,15,20];im[12:34,38:49]=[10,15,20]
  im[8:29,18:25]=[240,245,250];im[8:29,38:45]=[240,245,250]
  self.assertEqual(estimate_ink(im,[0,0,100,40]),[240,245,250])
 def test_white_text_on_dark_background(self):
  im=np.full((40,100,3),[20,40,60],np.uint8);im[10:30,20:25]=[235,245,255];im[10:30,35:40]=[235,245,255]
  self.assertEqual(estimate_ink(im,[0,0,100,40]),[235,245,255])
 def test_dark_text_on_light_background(self):
  im=np.full((40,100,3),[160,240,240],np.uint8);im[10:30,20:25]=[0,30,130]
  self.assertEqual(estimate_ink(im,[0,0,100,40]),[0,30,130])
 def test_thick_text_does_not_treat_text_majority_as_background(self):
  im=np.full((40,100,3),[160,240,240],np.uint8);im[3:37,3:97]=[0,30,130]
  self.assertEqual(estimate_ink(im,[0,0,100,40]),[0,30,130])

if __name__=='__main__':unittest.main()
