import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import native_host

class NativeConnectionRecoveryTests(unittest.TestCase):
 def test_live_engine_connection_takes_priority_over_stale_disk_record(self):
  calls=[]
  def urlopen(req,timeout):
   calls.append(req if isinstance(req,str) else req.full_url)
   if calls[-1].endswith('/connection'):return io.BytesIO(json.dumps({'url':'http://127.0.0.1:19217','token':'live-token'}).encode())
   self.assertEqual(req.get_header('X-shijie-token'),'live-token')
   return io.BytesIO(b'{"service":"shijie-engine","version":"0.9.0","ready":true}')
  with tempfile.TemporaryDirectory() as folder,patch.object(native_host,'STATE',Path(folder)),patch('urllib.request.urlopen',side_effect=urlopen),patch('subprocess.Popen') as start:
   (Path(folder)/'service.json').write_text('{"service":"shijie-engine","port":19217,"token":"stale-token"}')
   result=native_host.connect();self.assertEqual(result['token'],'live-token');start.assert_not_called()
  self.assertTrue(calls[0].endswith('/connection'))
 def test_invalid_live_connection_never_returns_credentials(self):
  with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"url":"https://other","token":"x"}')):
   self.assertIsNone(native_host.probe_running())

if __name__=='__main__':unittest.main()
