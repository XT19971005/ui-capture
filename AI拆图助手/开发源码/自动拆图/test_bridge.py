"""No registry mutations, no live browser profile, no paid calls."""
import ast, json, sys, unittest
from pathlib import Path
import server
class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.c=server.app.test_client();self.headers={'Host':'127.0.0.1:19217','X-Shijie-Token':server.TOKEN,'Origin':next(iter(server.ALLOWED_ORIGINS))}
 def test_public_ping_has_no_token(self):
  r=self.c.get('/ping',headers={'Host':'127.0.0.1:19217'});self.assertEqual(r.status_code,200);self.assertNotIn('token',r.json)
 def test_favicon_is_public_static_asset(self):
  r=self.c.get('/favicon.ico',headers={'Host':'127.0.0.1:19217'})
  self.assertEqual(r.status_code,200)
  self.assertEqual(r.data,(server.ROOT/'插件程序/edge/favicon.ico').read_bytes())
  r.close()
 def test_auth_and_origin(self):
  self.assertEqual(self.c.get('/health',headers={'Host':'127.0.0.1:19217'}).status_code,401)
  h={**self.headers,'Origin':'https://unrelated.example'};self.assertEqual(self.c.get('/health',headers=h).status_code,403)
  h={**self.headers,'Host':'attacker.example'};self.assertEqual(self.c.get('/health',headers=h).status_code,403)
  self.assertEqual(self.c.get('/health',headers=self.headers).status_code,200)
 def test_parameters(self):
  for data in [None,{'image':'bad'}, {'image':'data:image/png;base64,AA==','command':'shell'}]:
   self.assertEqual(self.c.post('/jobs',json=data,headers=self.headers).status_code,400)
 def test_cors(self):
  r=self.c.options('/jobs',headers=self.headers);self.assertEqual(r.status_code,204);self.assertEqual(r.headers['Access-Control-Allow-Origin'],self.headers['Origin'])
 def test_single_job_and_cancel(self):
  import threading
  server.jobs['fixture']={'status':'running','progress':.2,'message':'test','cancel':threading.Event()}
  try:
   r=self.c.post('/jobs',json={'image':'data:image/png;base64,AA=='},headers=self.headers);self.assertEqual(r.status_code,409)
   self.assertEqual(self.c.delete('/jobs/fixture',headers=self.headers).status_code,200);self.assertTrue(server.jobs['fixture']['cancel'].is_set())
   self.assertNotIn('cancel',self.c.get('/jobs/fixture',headers=self.headers).json)
  finally:server.jobs.clear()
 def test_syntax(self):
  for p in Path(__file__).parent.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
 def test_download_is_the_independently_audited_psd_and_rejects_tampering(self):
  import hashlib,tempfile
  from unittest.mock import patch
  with tempfile.TemporaryDirectory(dir=server.ROOT/'依赖/运行临时') as folder:
   project=Path(folder);structure=project/'1_过程/02_结构';qa=project/'1_过程/03_检查';out=project/'2_输出'
   for p in (structure,qa,out):p.mkdir(parents=True)
   psd=out/'verified.psd';psd.write_bytes(b'audited PSD bytes');file=structure/'工程.scene.json';file.write_text(json.dumps({'nodes':[{'name':'fixture layer'}],'recognition':{'reviewStatus':'PASS'},'delivery':{'psd':str(psd)}}),'utf8')
   (qa/'检查结果.json').write_text(json.dumps({'psdSHA256':hashlib.sha256(psd.read_bytes()).hexdigest(),'structuralChecks':'PASS','assetChecks':'PASS'}),'utf8')
   check={'name':'fixture layer','status':'PASS','notes':'test-only HTTP gate record, not visual acceptance'}
   (qa/'Codex画面复核.json').write_text(json.dumps({'status':'PASS','asset_checks':[check],'file_checks':[check]}),'utf8')
   (qa/'画面复核.json').write_text(json.dumps({'psdSHA256':hashlib.sha256(psd.read_bytes()).hexdigest(),'checks':[check]}),'utf8')
   with patch.object(server,'stored_projects',return_value={'fixture':file}):
    response=self.c.get('/projects/fixture/psd',headers=self.headers);self.assertEqual(response.status_code,200);self.assertEqual(response.data,psd.read_bytes());response.close()
    psd.write_bytes(b'changed');self.assertEqual(self.c.get('/projects/fixture/psd',headers=self.headers).status_code,409)
 def test_persistent_download_requires_actual_visual_records(self):
  import tempfile
  from unittest.mock import patch
  from test_session_outputs import fixture
  with tempfile.TemporaryDirectory(dir=server.ROOT/'依赖/运行临时') as folder:
   scene,_=fixture(Path(folder));project=Path(scene['delivery']['project']);file=project/'1_过程/02_结构/工程.scene.json';file.parent.mkdir();file.write_text(json.dumps(scene),'utf8');qa=project/'1_过程/03_检查'
   with patch.object(server,'stored_projects',return_value={'visual-fixture':file}):
    response=self.c.get('/projects/visual-fixture/psd',headers=self.headers);self.assertEqual(response.status_code,200);response.close()
    visual=qa/'Codex画面复核.json';visual.write_text(json.dumps({'status':'NEEDS_REVIEW'}),'utf8')
    self.assertEqual(self.c.get('/projects/visual-fixture/psd',headers=self.headers).status_code,409)
    visual.unlink();self.assertEqual(self.c.get('/projects/visual-fixture/psd',headers=self.headers).status_code,409)
if __name__=='__main__':unittest.main()
