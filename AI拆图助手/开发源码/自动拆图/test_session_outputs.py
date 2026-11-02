import hashlib,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import session_outputs as outputs

def fixture(home):
 p=home/'测试';q=p/'1_过程/03_检查';o=p/'2_输出';q.mkdir(parents=True);o.mkdir()
 raw=b'actual independently audited PSD';psd=o/'测试.psd';psd.write_bytes(raw)
 (q/'检查结果.json').write_text(json.dumps({'structuralChecks':'PASS','assetChecks':'PASS','psdSHA256':hashlib.sha256(raw).hexdigest()}),'utf8')
 check={'name':'synthetic text fixture','status':'PASS','notes':'test-only gate record, not a visual acceptance claim'}
 (q/'Codex画面复核.json').write_text(json.dumps({'status':'PASS','asset_checks':[check],'file_checks':[check]}),'utf8')
 (q/'画面复核.json').write_text(json.dumps({'psdSHA256':hashlib.sha256(raw).hexdigest(),'checks':[check]}),'utf8')
 return {'nodes':[{'name':check['name'],'type':'text','text':'可编辑'}],'recognition':{'reviewStatus':'PASS'},'_projectId':'old','delivery':{'project':str(p),'psd':str(psd),'original':str(o/'原图.jpg')}},raw

class SessionTests(unittest.TestCase):
 def test_needs_review_keeps_audited_psd_without_claiming_visual_pass(self):
  def generate(home):
   scene,_=fixture(home);scene['recognition']['reviewStatus']='NEEDS_REVIEW'
   scene['recognition']['reviewSummary']='个别素材偏色';return scene
  scene=outputs.run_temporary(generate);entry=outputs.SESSIONS.get(scene['_sessionId'])
  self.assertEqual(entry['psd'],b'actual independently audited PSD')
  self.assertEqual(entry['scene']['recognition']['reviewStatus'],'NEEDS_REVIEW')
  self.assertEqual(entry['audit']['visualStatus'],'NEEDS_REVIEW')
 def tearDown(self):outputs.SESSIONS.clear()
 def test_success_cleans_work_and_keeps_exact_bytes_only_in_ram(self):
  paths=[]
  def generate(home):paths.append(home);return fixture(home)[0]
  scene=outputs.run_temporary(generate)
  self.assertFalse(paths[0].exists());self.assertNotIn('_projectId',scene)
  self.assertEqual(scene['delivery']['storage'],'memory');self.assertNotIn('project',scene['delivery'])
  entry=outputs.SESSIONS.get(scene['_sessionId']);self.assertEqual(entry['psd'],b'actual independently audited PSD')
  self.assertEqual(entry['scene'],scene)
 def test_error_and_cancel_cleanup(self):
  for error in (ValueError('failed'),InterruptedError('cancel')):
   paths=[]
   def generate(home):paths.append(home);fixture(home);raise error
   with self.assertRaises(type(error)):outputs.run_temporary(generate)
   self.assertFalse(paths[0].exists());self.assertEqual(outputs.SESSIONS.count(),0)
 def test_audit_failure_never_keeps_download(self):
  def generate(home):scene,_=fixture(home);Path(scene['delivery']['psd']).write_bytes(b'changed');return scene
  with self.assertRaises(ValueError):outputs.run_temporary(generate)
  self.assertEqual(outputs.SESSIONS.count(),0)
 def test_expiration_and_consumption(self):
  scene=outputs.run_temporary(lambda home:fixture(home)[0]);ident=scene['_sessionId']
  self.assertIsNotNone(outputs.SESSIONS.take(ident));self.assertIsNone(outputs.SESSIONS.get(ident))
  store=outputs.SessionStore(ttl=.01);store.put({'nodes':[]},None);time.sleep(.03);self.assertEqual(store.count(),0)
 def test_missing_actual_visual_record_rejects_psd(self):
  def generate(home):
   scene,_=fixture(home);(Path(scene['delivery']['project'])/'1_过程/03_检查/Codex画面复核.json').unlink();return scene
  with self.assertRaises(FileNotFoundError):outputs.run_temporary(generate)
  self.assertEqual(outputs.SESSIONS.count(),0)
 def test_cleanup_failure_does_not_publish_ram_session(self):
  real=tempfile.TemporaryDirectory
  class CleanupFailure:
   def __init__(self,*args,**kwargs):self.temp=real(*args,**kwargs)
   def __enter__(self):return self.temp.__enter__()
   def __exit__(self,*args):self.temp.__exit__(*args);raise OSError('test-only cleanup failure')
  with patch.object(outputs.tempfile,'TemporaryDirectory',CleanupFailure):
   with self.assertRaises(OSError):outputs.run_temporary(lambda home:fixture(home)[0])
  self.assertEqual(outputs.SESSIONS.count(),0)
 def test_http_scene_download_release(self):
  import server
  client=server.app.test_client();h={'Host':'127.0.0.1:19217','X-Shijie-Token':server.TOKEN}
  scene=outputs.run_temporary(lambda home:fixture(home)[0]);ident=scene['_sessionId']
  self.assertEqual(client.get('/sessions/'+ident+'/scene',headers=h).json['nodes'],scene['nodes'])
  response=client.get('/sessions/'+ident+'/psd',headers=h);self.assertEqual(response.status_code,200)
  self.assertEqual(response.data,b'actual independently audited PSD');self.assertEqual(response.headers['X-Shijie-PSD-SHA256'],scene['delivery']['psdSHA256'])
  self.assertEqual(client.get('/sessions/'+ident+'/psd',headers=h).status_code,404)
  self.assertEqual(client.delete('/sessions/'+ident,headers=h).status_code,200)
 def test_capture_cross_page_is_ram_only_and_consumed(self):
  import base64,io,server
  from PIL import Image
  buffer=io.BytesIO();Image.new('RGB',(2,2),'red').save(buffer,format='PNG');src='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
  c=server.app.test_client();h={'Host':'127.0.0.1:19217','X-Shijie-Token':server.TOKEN}
  response=c.post('/captures',json={'image':src,'title':'测试框选'},headers=h);self.assertEqual(response.status_code,201)
  ident=response.json['id'];received=c.get('/captures/'+ident,headers=h)
  self.assertEqual(received.json['src'],src);self.assertEqual(received.json['title'],'测试框选');self.assertIsInstance(received.json['created'],int)
  self.assertEqual(c.get('/captures/'+ident,headers=h).status_code,404);self.assertEqual(c.delete('/captures/'+ident,headers=h).status_code,200)
  for invalid in ('data:image/svg+xml;base64,AA==','data:image/png;base64,AA==','https://example.com/p.png'):
   self.assertEqual(c.post('/captures',json={'image':invalid},headers=h).status_code,400)
if __name__=='__main__':unittest.main()
