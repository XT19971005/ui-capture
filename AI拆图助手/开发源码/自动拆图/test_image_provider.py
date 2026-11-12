import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
import image_provider as p
class ImageProviderTests(unittest.TestCase):
 def test_default_retains_codex_without_reading_credentials(self):
  with tempfile.TemporaryDirectory() as d,patch.object(p,'CONFIG',Path(d)/'config.json'):
   self.assertEqual(p.settings()['provider'],'codex')
 def test_encrypted_drama_key_not_exposed_by_status(self):
  with patch.object(p,'settings',return_value={'provider':'codex','model':'gpt-image-2','keyEncrypted':'secret'}),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]):
   value=p.status();self.assertNotIn('keyEncrypted',value);self.assertTrue(value['configured'])
 def test_unadapted_model_never_saved(self):
  with self.assertRaises(ValueError):p.save({'provider':'aimake','model':'random-image'})
 def test_codex_proxy_delegates_without_aimake_network(self):
  with patch.object(p,'settings',return_value={'provider':'codex'}),patch('codex_client.CLIENT.generate',return_value={'ok':True}) as call:
   self.assertEqual(p.CLIENT.generate('test',[],'target'),{'ok':True});self.assertEqual(call.call_count,1)
 def test_cancelled_generation_never_uploads_or_submits(self):
  with patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2'}),patch.object(p,'key',return_value='private'),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]),patch.object(p,'upload') as upload,patch.object(p,'request') as request:
   with self.assertRaises(InterruptedError):p.generate('test',[],Path('unused'),cancelled=lambda:True)
   upload.assert_not_called();request.assert_not_called()
 def test_uncertain_submission_retains_receipt_and_never_retries(self):
  with tempfile.TemporaryDirectory() as d,patch.object(p,'model_schema',return_value={'input':{'properties':{'prompt':{},'size':{},'aspect_ratio':{'enum':['1:1']},'ref_images':{},'input_images':{}}}}),patch.object(p,'STATE',Path(d)),patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2'}),patch.object(p,'key',return_value='private'),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]),patch.object(p,'request',side_effect=ValueError('transport failed')) as request:
   with self.assertRaises(ValueError):p.generate('test',[],Path(d)/'output.png')
   self.assertEqual(request.call_count,1);record=json.loads(next(Path(d).glob('亿创任务_*.json')).read_text('utf-8'));self.assertEqual(record['state'],'uncertain');self.assertNotIn('private',json.dumps(record))
 def test_cancel_after_final_upload_never_submits_paid_generation(self):
  stopped=False
  def upload(*args):
   nonlocal stopped
   stopped=True;return 'https://storage.example/reference.png'
  with patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2'}),patch.object(p,'key',return_value='private'),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]),patch.object(p,'dimensions',return_value={'width':1024,'height':1024}),patch('PIL.Image.open',return_value=Image.new('RGB',(1024,1024))),patch.object(p,'model_schema',return_value={'input':{'properties':{'prompt':{},'size':{},'aspect_ratio':{'enum':['1:1']},'ref_images':{},'input_images':{}}}}),patch.object(p,'upload',side_effect=upload),patch.object(p,'request') as request:
   with self.assertRaises(InterruptedError):p.generate('test',['reference.png'],Path('unused'),cancelled=lambda:stopped)
   request.assert_not_called()
 def test_unsupported_source_ratio_is_rejected_before_upload_or_generation(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/'source.png';Image.new('RGB',(50,250)).save(file)
   with self.assertRaises(ValueError):p.dimensions([file])
 def test_same_reference_upload_is_reused_without_duplicate_signing(self):
  class Put:
   status_code=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/'reference.png';file.write_bytes(b'unique upload fixture')
   with patch.object(p,'_uploads',{}),patch.object(p,'safe_https',side_effect=lambda url:url),patch.object(p,'request',side_effect=[{'method':'PUT','upload_url':'https://storage.example/put','headers':{},'object_key':'owned'}, {'url':'https://storage.example/reference.png'}]) as request,patch('requests.put',return_value=Put()) as put:
    first=p.upload(file,'fixture-secret',lambda:False);self.assertEqual(p.upload(file,'fixture-secret',lambda:False),first);self.assertEqual(request.call_count,2);self.assertEqual(put.call_count,1);self.assertNotIn('X-API-KEY',put.call_args.kwargs['headers']);self.assertEqual(file.read_bytes(),b'unique upload fixture')
 def test_custom_dimensions_preserve_reference_ratio_and_api_limits(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/'source.png';Image.new('RGB',(586,700)).save(file);shape=p.dimensions([file]);self.assertEqual(shape['width']%16,0);self.assertEqual(shape['height']%16,0);self.assertGreaterEqual(shape['width']*shape['height'],655360);self.assertLess(abs(shape['width']/shape['height']-586/700)/(586/700),.001)
 def test_storage_url_rejects_non_https_and_local_network(self):
  for url in ['http://example.com/a','https://user:pass@example.com/a','https://127.0.0.1/file']:
   with self.assertRaises(ValueError):p.safe_https(url)
if __name__=='__main__':unittest.main()

class FidelityTransportTests(unittest.TestCase):
 def test_large_reference_does_not_collapse_to_one_megapixel(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'reference.png';Image.new('RGB',(2048,2048)).save(file)
   self.assertEqual(p.dimensions([file]),{'width':2048,'height':2048})
 def test_small_reference_uses_smallest_valid_area_instead_of_unnecessary_upscale(self):
  from PIL import Image
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'reference.png';Image.new('RGB',(320,320)).save(file)
   shape=p.dimensions([file]);self.assertLess(shape['width']*shape['height'],700000)
 def test_pixelcut_stage_does_not_inject_flowers_or_conflicting_transparency(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(p,'key',return_value='test'),patch.object(p,'request',return_value=[{'id':'pixelcut-background-removal'}]),patch.object(p,'generate',return_value={}) as generate,patch.object(p,'remove_background',return_value={'size':[1024,1024]}):
   p.generate_transparent('仅提取战斧，其他对象和背景全部透明。',[],Path(folder)/'output.png',lambda:False,900,None)
   prompt=generate.call_args.args[0]
   self.assertNotIn('花瓣',prompt);self.assertIn('仅提取战斧',prompt)
   self.assertIn('本阶段背景使用纯白',prompt);self.assertIn('冲突',prompt)

class PixelcutResidueTests(unittest.TestCase):
 def test_only_remote_tiny_black_one_alpha_islands_are_removed(self):
  im=Image.new('RGBA',(100,80));im.paste((200,140,40,255),(30,25,70,60));im.putpixel((2,2),(0,0,0,1));im.putpixel((29,30),(0,0,0,1));im.putpixel((4,70),(20,80,200,1));im.putpixel((8,72),(0,0,0,2))
  fixed,count=p.clean_pixelcut_residue(im)
  self.assertEqual(count,1);self.assertEqual(fixed.getpixel((2,2))[3],0)
  for xy in [(29,30),(4,70),(8,72),(40,40)]:self.assertEqual(fixed.getpixel(xy),im.getpixel(xy))
  self.assertEqual(im.getpixel((2,2))[3],1)
 def test_large_faint_shadow_and_all_low_alpha_material_are_preserved(self):
  im=Image.new('RGBA',(100,80));im.paste((200,140,40,255),(30,25,70,60));im.paste((0,0,0,1),(2,2,12,3))
  fixed,count=p.clean_pixelcut_residue(im);self.assertEqual(count,0);self.assertEqual(fixed.tobytes(),im.tobytes())
  faint=Image.new('RGBA',(30,30),(0,0,0,1));fixed,count=p.clean_pixelcut_residue(faint);self.assertEqual(count,0);self.assertEqual(fixed.tobytes(),faint.tobytes())

class OpaqueInteriorTests(unittest.TestCase):
 def test_explicit_opaque_repair_fixes_interior_but_preserves_rgb_edges_and_holes(self):
  im=Image.new('RGBA',(50,50));im.paste((40,40,48,253),(5,5,45,45));im.putpixel((25,25),(0,0,0,0));im.putpixel((5,20),(220,220,220,100));im.putpixel((1,1),(40,40,50,80))
  fixed,count=p.repair_opaque_interior(im,expected_opaque=True)
  self.assertGreater(count,0);self.assertEqual(fixed.getpixel((15,15)),(40,40,48,255));self.assertEqual(fixed.getpixel((25,25)),im.getpixel((25,25)));self.assertEqual(fixed.getpixel((5,20)),im.getpixel((5,20)));self.assertEqual(fixed.getpixel((1,1)),im.getpixel((1,1)));self.assertEqual(fixed.getpixel((5,10)),im.getpixel((5,10)));self.assertEqual(im.getpixel((15,15))[3],253)
 def test_no_material_confirmation_and_genuinely_translucent_regions_are_unchanged(self):
  im=Image.new('RGBA',(20,20),(80,90,100,253));fixed,count=p.repair_opaque_interior(im);self.assertEqual(count,0);self.assertEqual(fixed.tobytes(),im.tobytes())
  im=Image.new('RGBA',(20,20),(80,90,100,180));fixed,count=p.repair_opaque_interior(im,expected_opaque=True);self.assertEqual(count,0);self.assertEqual(fixed.tobytes(),im.tobytes())
