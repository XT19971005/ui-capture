import threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import image_provider as p

class PreflightTests(unittest.TestCase):
 def test_generation_does_not_scan_every_model_before_upload(self):
  with patch.object(p,'key',return_value='fixture'),patch.object(p,'settings',return_value={'provider':'aimake','model':'gpt-image-2','key':'fixture'}),patch.object(p,'catalog',side_effect=AssertionError('full catalog scan')),patch.object(p,'model_schema',return_value={'input':{}}) as schema,patch.object(p,'generation_input',side_effect=ValueError('stop before upload')):
   with self.assertRaisesRegex(ValueError,'stop before upload'):p.generate('素材',[],'unused.png')
   schema.assert_called_once_with('gpt-image-2','fixture')
 def test_parallel_objects_share_one_schema_request(self):
  start=threading.Barrier(6);calls=[]
  def request(*a,**k):calls.append(a[0]);time.sleep(.02);return {'input':{}}
  def lookup(_):start.wait();return p.model_schema('gpt-image-2','fixture-single-flight')
  with patch.object(p,'request',side_effect=request):
   with ThreadPoolExecutor(max_workers=6) as pool:values=list(pool.map(lookup,range(6)))
  self.assertEqual(calls,['/models/gpt-image-2/schema'])
  self.assertTrue(all(v is values[0] for v in values))
