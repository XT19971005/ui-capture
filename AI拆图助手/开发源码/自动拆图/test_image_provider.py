import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch,Mock
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
  with tempfile.TemporaryDirectory() as d,patch.object(p,'STATE',Path(d)),patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2'}),patch.object(p,'key',return_value='private'),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]),patch.object(p,'request',side_effect=ValueError('transport failed')) as request:
   with self.assertRaises(ValueError):p.generate('test',[],Path(d)/'output.png')
   self.assertEqual(request.call_count,1);record=json.loads(next(Path(d).glob('亿创任务_*.json')).read_text('utf-8'));self.assertEqual(record['state'],'uncertain');self.assertNotIn('private',json.dumps(record))
 def test_cancel_after_final_upload_never_submits_paid_generation(self):
  stopped=False
  def upload(*args):
   nonlocal stopped
   stopped=True;return 'https://storage.example/reference.png'
  with patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2'}),patch.object(p,'key',return_value='private'),patch.object(p,'catalog',return_value=[{'id':'gpt-image-2'}]),patch.object(p,'dimensions',return_value={'width':1024,'height':1024}),patch.object(p,'upload',side_effect=upload),patch.object(p,'request') as request:
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
