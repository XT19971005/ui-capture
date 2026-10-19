"""Offline boundary regressions; no real Codex worker or browser launch."""
import base64,hashlib,importlib.util,io,json,queue,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from codex_client import CodexClient
from web_capture import BrowserBridge
from session_outputs import SessionStore,_seal
from runtime import ROOT,TEMP

class LifecycleBoundaries(unittest.TestCase):
 def test_success_is_not_overwritten_by_EOF_or_late_error(self):
  for late in (False,True):
   client=CodexClient();state={'texts':[],'done':threading.Event(),'turn_id':'new'};client.turns['t']=state
   events=[{'method':'turn/completed','params':{'threadId':'t','turn':{'id':'new','status':'completed'}}}]
   if late:events.append({'method':'error','params':{'threadId':'t','turnId':'new','willRetry':False,'error':{'message':'late'}}})
   proc=SimpleNamespace(stdout=iter(json.dumps(e)+'\n' for e in events));client.proc=proc;client.read_loop(proc)
   self.assertNotIn('error',state);self.assertEqual(state['turn']['status'],'completed')
 def test_cancel_before_preflight_submits_no_turn(self):
  for kind in ('analyze','generate'):
   client=CodexClient()
   with patch.object(client,'call') as call,patch.object(client,'account',return_value={'ready':True}),patch.object(client,'model',return_value='mock'),tempfile.TemporaryDirectory(dir=TEMP) as home:
    with self.assertRaises(InterruptedError):
     if kind=='analyze':client.analyze('fixture',[],{},cancelled=lambda:True)
     else:client.generate('fixture',[],Path(home)/'image.png',cancelled=lambda:True)
    call.assert_not_called()
 def test_cancel_during_model_lookup_submits_no_thread(self):
  client=CodexClient();cancel=threading.Event()
  def model():cancel.set();return 'mock'
  with patch.object(client,'call') as call,patch.object(client,'account',return_value={'ready':True}),patch.object(client,'model',side_effect=model):
   with self.assertRaises(InterruptedError):client.analyze('fixture',[],{},cancelled=cancel.is_set)
   call.assert_not_called()
 def run_cancel(self,kind,instant=False,interrupt_fails=False):
  client=CodexClient();cancel=threading.Event();calls=[];buf=io.BytesIO();Image.new('RGBA',(2,2),(0,0,0,0)).save(buf,format='PNG')
  def call(method,params=None,**kwargs):
   calls.append(method)
   if method=='modelProvider/capabilities/read':return {'imageGeneration':True}
   if method=='thread/start':return {'thread':{'id':'t'}}
   if method=='turn/start':
    cancel.set()
    if instant:
     state=client.turns['t'];state.update(texts=['{"ok":true}'],images=[{'type':'imageGeneration','result':base64.b64encode(buf.getvalue()).decode()}],turn={'status':'completed'});state['done'].set()
    return {'turn':{'id':'turn'}}
   if method=='turn/interrupt' and interrupt_fails:raise RuntimeError('interrupt transport failed')
   return {}
  with tempfile.TemporaryDirectory(dir=TEMP) as home,patch.object(client,'call',side_effect=call),patch.object(client,'account',return_value={'ready':True}),patch.object(client,'model',return_value='mock'),patch.object(client,'close',return_value=True):
   with self.assertRaises(InterruptedError):
    if kind=='analyze':client.analyze('fixture',[],{},cancelled=cancel.is_set)
    else:client.generate('fixture',[],Path(home)/'out.png',cancelled=cancel.is_set)
  self.assertFalse(client.turns);self.assertEqual(calls.count('turn/start'),1)
 def test_cancel_at_completion_cannot_return_success(self):
  for kind in ('analyze','generate'):self.run_cancel(kind,instant=True)
 def test_cancel_during_final_image_validation_cannot_return_success(self):
  client=CodexClient();cancel=threading.Event();png=io.BytesIO();Image.new('RGBA',(2,2),(0,0,0,0)).save(png,format='PNG');real_open=Image.open
  def call(method,params=None,**kw):
   if method=='modelProvider/capabilities/read':return {'imageGeneration':True}
   if method=='thread/start':return {'thread':{'id':'final-validation'}}
   if method=='turn/start':
    state=client.turns['final-validation'];state.update(images=[{'type':'imageGeneration','result':base64.b64encode(png.getvalue()).decode()}],turn={'status':'completed'});state['done'].set();return {'turn':{'id':'t'}}
   return {}
  def image_open(*a,**kw):cancel.set();return real_open(*a,**kw)
  with tempfile.TemporaryDirectory(dir=TEMP) as home,patch.object(client,'call',side_effect=call),patch.object(client,'model',return_value='mock'),patch.object(client,'close',return_value=True),patch.object(Image,'open',side_effect=image_open):
   with self.assertRaises(InterruptedError):client.generate('fixture',[],Path(home)/'generated.png',cancelled=cancel.is_set)
 def test_interrupt_error_cannot_change_cancel_to_failure(self):
  for kind in ('analyze','generate'):self.run_cancel(kind,interrupt_fails=True)
 def test_timeout_preserves_manual_pages_and_cancels_own_capture(self):
  class Bridge(BrowserBridge):
   def __init__(self):super().__init__();self.process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO());self.manual_targets={'manual'};self.stopped=False;self.keys=[]
   def start(self):pass
   def stop(self):self.stopped=True;self.process=None
   def cancel(self,key):self.keys.append(key)
  b=Bridge()
  with patch.object(b.messages,'get',side_effect=queue.Empty):
   with self.assertRaisesRegex(RuntimeError,'超时'):b.call('capture',url='https://fixture.invalid',captureKey='own')
  self.assertFalse(b.stopped);self.assertEqual(b.keys,['own'])
 def test_session_get_is_detached(self):
  store=SessionStore();scene=store.put({'nodes':[]},b'fixture',audit={'checks':['original']});ident=scene['_sessionId']
  received=store.get(ident);received['psd']=b'changed';received['audit']['checks'].append('changed')
  self.assertEqual(store.get(ident)['psd'],b'fixture');self.assertEqual(store.get(ident)['audit']['checks'],['original'])
 def test_HTTP_download_rejects_bytes_changed_between_get_and_take(self):
  import server
  store=server.SESSIONS;scene=store.put({'nodes':[]},b'audited fixture');ident=scene['_sessionId'];take=store.take
  def changed(key):
   row=take(key)
   if row:row['psd']=b'changed after get'
   return row
  with patch.object(store,'take',side_effect=changed):
   r=server.app.test_client().get('/sessions/'+ident+'/psd',headers={'Host':'127.0.0.1:19217','X-Shijie-Token':server.TOKEN})
  self.assertEqual(r.status_code,409);self.assertIsNone(store.get(ident))
 def test_late_capture_reply_is_not_used_for_next_request(self):
  class Bridge(BrowserBridge):
   def __init__(self):super().__init__();self.process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO());self.manual_targets={'manual'}
   def start(self):pass
   def stop(self):self.process=None
  bridge=Bridge();replies=iter([{'id':'old-timed-out','ok':True,'result':{'data':'old'}},{'id':'new-request','ok':True,'result':{'data':'new'}}])
  with patch('web_capture.uuid.uuid4',return_value=SimpleNamespace(hex='new-request')),patch.object(bridge.messages,'get',side_effect=lambda **kw:next(replies)):
   result=bridge.call('capture',target='manual',captureKey='new-key')
  self.assertEqual(result['data'],'new')
 def test_seal_rejects_stale_visual_checklist_SHA(self):
  from test_session_outputs import fixture
  with tempfile.TemporaryDirectory(dir=TEMP) as home:
   home=Path(home);scene,raw=fixture(home);qa=Path(scene['delivery']['project'])/'1_过程/03_检查';check=json.loads((qa/'画面复核.json').read_text('utf8'));check['psdSHA256']=hashlib.sha256(b'stale').hexdigest();(qa/'画面复核.json').write_text(json.dumps(check),'utf8')
   with self.assertRaises(ValueError):_seal(scene,home)
 def test_share_rejects_credential_variants_but_keeps_runtime_auth_code(self):
  file=ROOT/'开发源码/分享打包/build_shijie_share.py';spec=importlib.util.spec_from_file_location('share',file);share=importlib.util.module_from_spec(spec);spec.loader.exec_module(share)
  for name in ('auth.json.bak','credentials.toml','token.yaml','auth.backup','token.json.old','auth.dat','credentials.zip','token.sqlite'):
   self.assertFalse(share.is_allowed(Path('拾界插件/开发源码/自动拆图')/name),name)
  self.assertTrue(share.is_allowed(Path('拾界插件/依赖/运行环境/python/site-packages/requests/auth.py')))

if __name__=='__main__':unittest.main()
