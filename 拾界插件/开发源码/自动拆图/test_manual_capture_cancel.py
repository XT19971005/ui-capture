"""Controlled localhost + owned headless browser; never touch user tabs or AI."""
import json,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from web_capture import BrowserBridge
from runtime import ROOT

class ManualCaptureCancel(unittest.TestCase):
 def test_slow_ready_cancel_retry_preserves_manual_and_URL_tasks(self):
  state={'slow':True,'pulses':0};bridge=BrowserBridge(headless=True);threads=[]
  class Fixture(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    if self.path.startswith('/pulse'):
     state['pulses']+=1;body=json.dumps({'slow':state['slow']}).encode();mime='application/json'
    else:
     slow='slow' in self.path or self.path=='/'
     body=('''<!doctype html><meta charset="utf-8"><title>手动页取消受控验证</title><p id="live">等待完成</p>'''+('''<script>const timer=setInterval(async()=>{const r=await fetch('/pulse?'+Date.now()).then(r=>r.json());document.getElementById('live').textContent=r.slow?'慢ready进行中':'重新抓取成功';if(!r.slow)clearInterval(timer)},120)</script>''' if slow else '<p>后台URL正常抓取</p>')).encode('utf8');mime='text/html; charset=utf-8'
    self.send_response(200);self.send_header('Content-Type',mime);self.end_headers()
    try:self.wfile.write(body)
    except (BrokenPipeError,ConnectionResetError):pass
  http=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=http.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(http.server_port)
  outcomes={};report={}
  def worker(label,**args):
   try:outcomes[label]={'result':bridge.call('capture',**args)}
   except Exception as e:outcomes[label]={'error':str(e)}
  try:
   opened=bridge.call('open',url=url+'/');ident=opened['id'];work=Path(bridge.temp.name)
   thread=threading.Thread(target=worker,kwargs={'label':'manual','target':ident,'captureKey':'manual-slow'});threads.append(thread);thread.start();time.sleep(.65)
   self.assertTrue(thread.is_alive(),'must cancel while actual ready is pending');pulses_before=state['pulses'];started=time.monotonic();bridge.cancel('manual-slow');thread.join(3)
   elapsed=time.monotonic()-started;self.assertFalse(thread.is_alive(),'cancellation must release Python/Node queue promptly');self.assertIn('取消',outcomes['manual'].get('error',''));self.assertIn(ident,bridge.manual_targets);self.assertIsNone(bridge.process.poll())
   state['slow']=False;time.sleep(.8);retry_started=time.monotonic();retry=bridge.call('capture',target=ident,captureKey='manual-retry');self.assertEqual(retry['target']['id'],ident);self.assertIn('重新抓取成功',json.dumps(retry['data'],ensure_ascii=False))
   report['manual']={'cancelledDuringRealSlowReady':True,'pulseRequestsBeforeCancel':pulses_before,'cancelSeconds':round(elapsed,3),'queueReleasedWithin3s':True,'retrySucceeded':True,'retrySeconds':round(time.monotonic()-retry_started,3),'manualPagePreserved':True}
   direct=bridge.call('capture',url=url+'/fast',captureKey='URL-success');self.assertIsNone(direct['target']);self.assertIn('后台URL正常抓取',json.dumps(direct['data'],ensure_ascii=False));self.assertIn(ident,bridge.manual_targets)
   state['slow']=True;thread=threading.Thread(target=worker,kwargs={'label':'URLcancel','url':url+'/urlslow','captureKey':'URL-slow'});threads.append(thread);thread.start();time.sleep(1.4);started=time.monotonic();bridge.cancel('URL-slow');thread.join(8)
   url_cancel_elapsed=time.monotonic()-started
   self.assertFalse(thread.is_alive());self.assertIn('取消',outcomes['URLcancel'].get('error',''));self.assertIn(ident,bridge.manual_targets)
   self.assertEqual(len(list(work.glob('browser-*'))),1,'only owned manual context remains after URL task cleanup')
   again=bridge.call('capture',target=ident,captureKey='manual-after-URL');self.assertEqual(again['target']['id'],ident)
   report['URL']={'normalBackgroundCapture':True,'cancelledBackgroundCapture':True,'cancelSeconds':round(url_cancel_elapsed,3),'ownFolderCleaned':True,'manualPageStillCapturable':True}
   bridge.call('close',target=ident);self.assertFalse(work.exists());report['allOwnedTemporaryFoldersCleaned']=True;report['status']='PASS'
  finally:
   state['slow']=False
   for thread in threads:thread.join(12)
   bridge.stop();http.shutdown();http.server_close()
  out=ROOT.parent/'测试结果/拾界_标准逐项自检';out.mkdir(parents=True,exist_ok=True);(out/'手动抓取取消_真实浏览器.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')

if __name__=='__main__':unittest.main()
