import unittest
from server import app, TOKEN
class WebCaptureRoutes(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()
        self.headers={'X-Shijie-Token':TOKEN,'Origin':'http://127.0.0.1:19217'}
    def test_invalid_link_is_rejected(self):
        r=self.client.post('/web/open',json={'url':'javascript:alert(1)'},headers=self.headers,base_url='http://127.0.0.1:19217')
        self.assertEqual(r.status_code,400)
    def test_capture_requires_open_target(self):
        r=self.client.post('/web/capture',json={},headers=self.headers,base_url='http://127.0.0.1:19217')
        self.assertEqual(r.status_code,400)
    def test_open_requires_local_token(self):
        r=self.client.post('/web/open',json={'url':'https://example.com'},base_url='http://127.0.0.1:19217')
        self.assertEqual(r.status_code,401)
if __name__=='__main__':unittest.main()
