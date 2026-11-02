import tempfile,unittest,base64
from pathlib import Path
from PIL import Image
from workflow_assets import image_node

class AssetPlacementTests(unittest.TestCase):
 def test_transparent_padding_does_not_shrink_visible_subject(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'fan.png';im=Image.new('RGBA',(200,200));im.paste((240,40,10,255),(50,75,150,125));im.save(file)
   n=image_node(file,'扇子',[10,20,100,50])
   self.assertEqual((n['x']+50*n['width']/200,n['y']+75*n['height']/200,n['width']*100/200,n['height']*50/200),(10,20,100,50))
   self.assertEqual(base64.b64decode(n['src'].split(',')[1]),file.read_bytes())
 def test_empty_alpha_cannot_become_a_successful_asset(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'empty.png';Image.new('RGBA',(100,100)).save(file)
   with self.assertRaisesRegex(ValueError,'透明'):image_node(file,'空素材',[0,0,100,100])
 def test_fixed_entity_roi_preserves_canvas_registration(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'union.png';im=Image.new('RGBA',(200,100));im.paste('red',(20,10,180,90));im.save(file)
   n=image_node(file,'联合实体',[0,0,400,200],preserve_canvas=True)
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(0,0,400,200))
 def test_transparent_asset_is_never_stretched_to_crop_ratio(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'asset.png';Image.new('RGBA',(80,40),(100,120,140,255)).save(file)
   n=image_node(file,'物品',[10,20,100,100])
   self.assertEqual(n['width']/n['height'],2)
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(10,45,100,50))
   self.assertEqual(base64.b64decode(n['src'].split(',')[1]),file.read_bytes())
 def test_opaque_background_covers_canvas_without_stretch(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'bg.png';Image.new('RGB',(80,40),'gray').save(file)
   n=image_node(file,'背景',[0,0,100,100],True)
   self.assertEqual(n['width']/n['height'],2)
   self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-50,0,200,100))
 def test_incompatible_generated_ratio_is_rejected_before_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'bg.png';Image.new('RGB',(80,1),'gray').save(file)
   with self.assertRaisesRegex(ValueError,'比例'):image_node(file,'背景',[0,0,100,6000],True)
 def test_cover_area_stays_within_native_six_megapixel_limit(self):
  with tempfile.TemporaryDirectory() as tmp:
   file=Path(tmp)/'bg.png';Image.new('RGB',(80,40),'gray').save(file)
   with self.assertRaisesRegex(ValueError,'比例'):image_node(file,'背景',[0,0,1600,3000],True)

if __name__=='__main__':unittest.main()
