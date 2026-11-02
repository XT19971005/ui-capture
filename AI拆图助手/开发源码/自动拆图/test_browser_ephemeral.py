import tempfile,unittest
from pathlib import Path
from web_capture import BrowserBridge
class BrowserEphemeralTests(unittest.TestCase):
 def test_real_browser_close_and_failure_leave_no_profile(self):
  from http.server import BaseHTTPRequestHandler,HTTPServer
  import threading
  class Page(BaseHTTPRequestHandler):
   def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'<title>ephemeral</title><p>editable capture</p>')
   def log_message(self,*args):pass
  http=HTTPServer(('127.0.0.1',0),Page);threading.Thread(target=http.serve_forever,daemon=True).start()
  with tempfile.TemporaryDirectory(prefix='shijie-browser-test-') as folder:
   forbidden=Path(folder)/'do-not-create-profile';bridge=BrowserBridge(headless=True,profile=forbidden)
   try:
    opened=bridge.call('open',url='http://127.0.0.1:'+str(http.server_port))
    work=Path(bridge.temp.name);self.assertTrue(any(work.iterdir()));self.assertFalse(forbidden.exists())
    capture=bridge.call('capture',target=opened['id']);self.assertEqual(capture['data']['title'],'ephemeral')
    second=bridge.call('open',url='http://127.0.0.1:'+str(http.server_port))
    bridge.call('close',target=opened['id']);self.assertTrue(work.exists());self.assertEqual(bridge.call('capture',target=second['id'])['data']['title'],'ephemeral')
    bridge.call('close',target=second['id']);self.assertFalse(work.exists());self.assertIsNone(bridge.temp);self.assertIsNone(bridge.process)
    with self.assertRaises(RuntimeError):bridge.call('open',url='http://127.0.0.1:1')
    self.assertIsNone(bridge.temp);self.assertIsNone(bridge.process)
   finally:bridge.stop();http.shutdown();http.server_close()
   self.assertFalse(work.exists());self.assertFalse(forbidden.exists())
if __name__=='__main__':unittest.main()
