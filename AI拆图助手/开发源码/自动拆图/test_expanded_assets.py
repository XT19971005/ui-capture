import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from expansion_geometry import margins
from expanded_assets import extract
class ExpandedTests(unittest.TestCase):
 def test_large_original_keeps_its_pixels_and_uses_safe_margins(self):
  mx,my=margins(2048,2048);self.assertGreater(mx,0);self.assertLessEqual((2048+2*mx)*(2048+2*my),6000000)
 def test_asset_can_extend_beyond_old_box_without_being_fitted_back(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   def generate(prompt,images,target,**kwargs):
    self.assertIn('不压缩',prompt);im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(25,10,125,140));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'完整袖子','extractionBrief':'保留完整袖子','x':10,'y':20,'width':30,'height':40},p,lambda:False,lambda *_:None)
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-20,-25,120,150))
 def test_clipped_outer_edge_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   def generate(prompt,images,target,**kwargs):
    im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(15,0,100,150));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'出画'):extract(source,{'id':'layer','name':'袖子','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
