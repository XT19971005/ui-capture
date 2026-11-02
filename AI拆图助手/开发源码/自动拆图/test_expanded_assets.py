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
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-35,-25,150,150))
 def test_clipped_outer_edge_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   def generate(prompt,images,target,**kwargs):
    im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(15,0,100,150));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'袖子','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertTrue(n['boundaryReviewRequired']);self.assertIn('可能不完整',n['reviewIssue'])

 def test_content_in_square_padding_expands_registration_without_losing_pixels(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(100,80)).save(source)
   def generate(prompt,images,target,**kwargs):
    im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(10,5,140,145));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'完整武器','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-25,-35,150,150))
   with Image.open(p/'layer_完整扩展.png') as im:
    self.assertEqual(im.getchannel('A').getbbox(),(10,5,140,145))
    self.assertEqual(sum(im.getchannel('A').getdata()),130*140*255)

 def test_generated_reference_and_full_visible_result_stay_under_pixel_limit(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(2048,1143)).save(source)
   def generate(prompt,images,target,**kwargs):
    with Image.open(images[0]) as ref:side=ref.width
    self.assertLessEqual(side*side,6000000)
    im=Image.new('RGBA',(side,side));im.paste((80,100,120,255),(50,50,side-50,side-50));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'大素材','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertLessEqual(n['width']*n['height'],6000000)
