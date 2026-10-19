"""Replay app-server disconnect notifications without paid/network generation."""
import base64,inspect,io,json,queue,threading,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
from codex_client import CodexClient,TEMP

class Pipe:
 def __init__(self):self.items=queue.Queue()
 def __iter__(self):return self
 def __next__(self):
  item=self.items.get(timeout=3)
  if item is None:raise StopIteration
  return json.dumps(item)+'\n'
 def put(self,method,params):self.items.put({'method':method,'params':params})

class ReconnectionTests(unittest.TestCase):
 def replay(self,kind,terminal=False,cancel=False):
  client=CodexClient();pipe=Pipe();proc=type('Proc',(),{'stdout':pipe})();client.proc=proc
  reader=threading.Thread(target=client.read_loop,args=(proc,),daemon=True);reader.start()
  log=[];notices=[];cancel_event=threading.Event();emitter=None
  buf=io.BytesIO();fixture=Image.new('RGBA',(4,4),(120,90,220,120));fixture.putpixel((0,0),(0,0,0,0));fixture.save(buf,format='PNG');raw=base64.b64encode(buf.getvalue()).decode()
  def call(method,params=None,**kwargs):
   nonlocal emitter
   log.append(method)
   if method=='modelProvider/capabilities/read':return {'imageGeneration':True}
   if method=='thread/start':return {'thread':{'id':'thread-fixture'}}
   if method=='turn/start':
    def emit():
     error={'message':'Reconnecting... 2/5','codexErrorInfo':{'responseStreamDisconnected':{'httpStatusCode':None}},'additionalDetails':'websocket closed before response.completed'}
     pipe.put('error',{'threadId':'thread-fixture','turnId':'turn-fixture','error':error,'willRetry':True})
     time.sleep(.05)
     if cancel:cancel_event.set();return
     if terminal:
      pipe.put('error',{'threadId':'thread-fixture','turnId':'turn-fixture','error':{**error,'message':'stream disconnected after retries'},'willRetry':False});return
     item={'type':'imageGeneration','result':raw} if kind=='generate' else {'type':'agentMessage','text':'{"status":"PASS"}'}
     pipe.put('item/completed',{'threadId':'thread-fixture','item':item})
     pipe.put('turn/completed',{'threadId':'thread-fixture','turn':{'id':'turn-fixture','status':'completed'}})
    emitter=threading.Thread(target=emit,daemon=True);emitter.start()
    return {'turn':{'id':'turn-fixture'}}
   return {}
  try:
   with TemporaryDirectory(prefix='reconnect-fixture-',dir=TEMP) as home,patch.object(client,'call',side_effect=call),patch.object(client,'account',return_value={'ready':True}),patch.object(client,'model',return_value='fixture'),patch.object(client,'close',return_value=True):
    method=client.generate if kind=='generate' else client.analyze
    callbacks={'on_status':notices.append} if 'on_status' in inspect.signature(method).parameters else {}
    if kind=='generate':result=client.generate('fixture',[],Path(home)/'asset.png',transparent=True,cancelled=cancel_event.is_set,**callbacks)
    else:result=client.analyze('fixture',[],{},cancelled=cancel_event.is_set,**callbacks)
    self.assertEqual(log.count('turn/start'),1,'retry must not launch duplicate billed generation')
    self.assertTrue(any('重连' in n for n in notices))
    self.assertTrue(any('恢复' in n for n in notices))
    self.assertFalse(client.turns)
    return result
  finally:
   if emitter:emitter.join(timeout=2)
   client.proc=None;pipe.items.put(None);reader.join(timeout=2)
 def test_generation_retry_notification_is_not_terminal(self):self.assertTrue(self.replay('generate')['actualImageGeneration'])
 def test_analysis_recovers_in_same_turn(self):self.assertEqual(self.replay('analyze'),{'status':'PASS'})
 def test_exhausted_retry_has_readable_error(self):
  with self.assertRaisesRegex(RuntimeError,'Codex 连接中断'):self.replay('generate',terminal=True)
 def test_cancel_still_works_during_reconnection(self):
  with self.assertRaises(InterruptedError):self.replay('generate',cancel=True)

if __name__=='__main__':unittest.main()
