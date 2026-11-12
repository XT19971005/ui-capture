import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import rgba_batch, vector_candidate, validate_plan, clear_text


class CoreTests(unittest.TestCase):
    def test_rgba_and_comfy_mask(self):
        im = np.ones((1, 8, 8, 4), np.float32)
        im[..., 3] = .3
        self.assertEqual(int(rgba_batch(im)[0][0, 0, 3]), 76)
        rgb = im[..., :3]
        self.assertEqual(int(rgba_batch(rgb, np.ones((1,8,8)))[0][0,0,3]), 0)
        with self.assertRaises(ValueError):
            rgba_batch(np.ones((2,8,8,3)), np.ones((3,8,8)))

    def test_shadow_never_vector(self):
        im = np.zeros((32,32,4), np.uint8); im[2:30,2:30] = [20,20,20,100]
        self.assertIsNone(vector_candidate(im))

    def test_flat_shape_retains_hole(self):
        im = np.zeros((64,64,4), np.uint8)
        im[4:60,4:60] = [12,30,90,255]; im[20:44,20:44] = 0
        shape = vector_candidate(im)
        self.assertTrue(any(p['operation'] == 'subtract' for p in shape['shapes']))
        self.assertIn('C', shape['shapes'][0]['d'])

    def test_reject_colored_art(self):
        im = np.zeros((32,32,4), np.uint8); im[:16] = [255,0,0,255];im[16:] = [0,0,255,255]
        self.assertIsNone(vector_candidate(im))

    def test_subtle_gradient_is_not_solid(self):
        im=np.full((64,64,4),255,np.uint8)
        im[...,:3]=np.arange(64,dtype=np.uint8)[None,:,None]//7+120
        self.assertIsNone(vector_candidate(im))

    def test_sparse_colored_detail_is_not_discarded(self):
        im=np.full((100,100,4),255,np.uint8);im[20:25,20:25,:3]=0
        self.assertIsNone(vector_candidate(im))

    def test_plan_validation(self):
        with self.assertRaises(ValueError):
            validate_plan({'texts':[{'text':'x','box':[-1,0,12,20]}]},32,32)
        with self.assertRaises(ValueError):
            validate_plan({'texts':[{'text':'x','box':[0,0,10,20],'font_file':'../../secret'}]},32,32)

    def test_text_clear_bounded_and_shadow_untouched(self):
        im = np.zeros((30,30,4),np.uint8);im[3:8,3:8]=[0,0,90,255];im[20:,20:]=[0,0,90,90]
        clean = clear_text(im, {'box':[2,2,10,10],'color':[0,0,90]})
        self.assertEqual(int(clean[4,4,3]),0)
        np.testing.assert_array_equal(clean[15:,15:],im[15:,15:])

if __name__ == '__main__': unittest.main()
