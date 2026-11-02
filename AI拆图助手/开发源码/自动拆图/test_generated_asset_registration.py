import base64,io,tempfile,unittest
from pathlib import Path
from PIL import Image
from expanded_assets import register_asset
class RegistrationTests(unittest.TestCase):
 def test_landscape_portrait_and_square_keep_original_png_bytes_and_aspect(self):
  for size in [(160,90),(90,160),(120,120)]:
   with self.subTest(size=size),tempfile.TemporaryDirectory() as folder:
    target=Path(folder)/'asset.png';im=Image.new('RGBA',size);im.paste((255,100,10,80),(2,2,size[0]-2,size[1]-2));im.save(target);raw=target.read_bytes()
    n=register_asset(target,200,(-30,-40))
    self.assertEqual(base64.b64decode(n['src'].split(',',1)[1]),raw)
    self.assertAlmostEqual(n['width']/n['height'],size[0]/size[1])
    self.assertEqual(n['positionReviewRequired'],size[0]!=size[1])
 def test_faint_glow_and_edge_pixels_are_retained_and_edge_is_flagged(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'asset.png';im=Image.new('RGBA',(160,90));im.putpixel((0,30),(255,120,10,1));im.putpixel((80,40),(255,120,10,200));im.save(p)
   n=register_asset(p,200,(0,0));self.assertTrue(n['boundaryReviewRequired'])
   with Image.open(io.BytesIO(base64.b64decode(n['src'].split(',',1)[1]))) as actual:self.assertEqual(actual.getpixel((0,30))[3],1)
 def test_empty_or_fake_transparency_is_rejected(self):
  for color in [(0,0,0,0),(0,0,0,255)]:
   with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'asset.png';Image.new('RGBA',(20,20),color).save(p)
    with self.assertRaises(ValueError):register_asset(p,100,(0,0))
