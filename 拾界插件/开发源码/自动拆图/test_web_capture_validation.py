import unittest
from unittest.mock import patch
from server import app,TOKEN

class CaptureInputValidation(unittest.TestCase):
 def test_non_object_json_rejected_without_browser_work(self):
  client=app.test_client();bridge=app.extensions['shijie_web_capture']
  with patch.object(bridge,'call') as call,patch.object(bridge,'cancel') as cancel:
   for route in ('open','capture','close','cancel'):
    for body in ([1],'text',True):
     with self.subTest(route=route,body=body):
      response=client.post('/web/'+route,json=body,base_url='http://127.0.0.1:19217',headers={'X-Shijie-Token':TOKEN})
      self.assertEqual(response.status_code,400)
   call.assert_not_called();cancel.assert_not_called()
 def test_capture_cancel_keys_are_bounded_strings(self):
  client=app.test_client();bridge=app.extensions['shijie_web_capture']
  with patch.object(bridge,'call') as call,patch.object(bridge,'cancel') as cancel:
   for key in ([],{},123,'x'*129):
    for route in ('capture','cancel'):
     with self.subTest(route=route,key=key):
      response=client.post('/web/'+route,json={'url':'https://fixture.invalid/','captureKey':key},base_url='http://127.0.0.1:19217',headers={'X-Shijie-Token':TOKEN})
      self.assertEqual(response.status_code,400)
   call.assert_not_called();cancel.assert_not_called()
 def test_malformed_ipv6_url_is_a_client_error(self):
  response=app.test_client().post('/web/capture',json={'url':'https://[bad'},base_url='http://127.0.0.1:19217',headers={'X-Shijie-Token':TOKEN})
  self.assertEqual(response.status_code,400)

if __name__=='__main__':unittest.main()
