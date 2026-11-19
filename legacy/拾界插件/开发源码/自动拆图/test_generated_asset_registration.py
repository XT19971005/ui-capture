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
 def test_faint_glow_and_edge_pixels_are_retained_without_false_clipped_shape(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'asset.png';im=Image.new('RGBA',(160,90));im.putpixel((0,30),(255,120,10,1));im.putpixel((80,40),(255,120,10,200));im.save(p)
   n=register_asset(p,200,(0,0));self.assertFalse(n['boundaryReviewRequired'])
   with Image.open(io.BytesIO(base64.b64decode(n['src'].split(',',1)[1]))) as actual:self.assertEqual(actual.getpixel((0,30))[3],1)
 def test_empty_or_fake_transparency_is_rejected(self):
  for color in [(0,0,0,0),(0,0,0,255)]:
   with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'asset.png';Image.new('RGBA',(20,20),color).save(p)
    with self.assertRaises(ValueError):register_asset(p,100,(0,0))

 def test_semantic_match_receives_object_scope_and_exclusions_without_relaxing_fit(self):
  from semantic_registration import calibrate_semantic
  reference=Image.new('RGB',(200,120),'white');generated=Image.new('RGBA',(160,100));generated.paste((230,160,40,255),(10,10,150,90));captured=[]
  def analyze(prompt,images,schema,**kwargs):
   captured.append(prompt)
   self.assertIn('排除英文副标题',prompt);self.assertIn('不得作为缺失主体的证据',prompt)
   return {'sameObject':False,'confidence':.95,'reason':'主星芒被拉长','anchors':[]}
  with self.assertRaisesRegex(ValueError,'主星芒被拉长'):
   calibrate_semantic(reference,generated,{'x':10,'y':10,'width':160,'height':90,'name':'标题','extractionBrief':'只取中文金字，排除英文副标题'}, {'name':'标题'},analyze=analyze)
  self.assertEqual(len(captured),1)
