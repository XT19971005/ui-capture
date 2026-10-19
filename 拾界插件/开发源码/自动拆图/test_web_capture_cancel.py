"""A queued cancellation must prevent navigation and preserve other manual pages."""
import io, threading, unittest
from types import SimpleNamespace
from web_capture import BrowserBridge

class FakeBridge(BrowserBridge):
 def __init__(self):super().__init__();self.started=0
 def start(self):
  self.started+=1
  self.process=SimpleNamespace(stdin=io.StringIO(),poll=lambda:None)
  self.messages.put({'ok':True,'result':{'remaining':1}})
 def stop(self):self.process=None

class QueuedCancelTests(unittest.TestCase):
 def test_cancel_before_process_exists_prevents_start(self):
  bridge=FakeBridge();bridge.cancel('not-started')
  with self.assertRaisesRegex(RuntimeError,'取消'):bridge.call('capture',url='https://fixture.invalid/',captureKey='not-started')
  self.assertEqual(bridge.started,0)
 def test_cancel_while_waiting_for_bridge_lock_prevents_start(self):
  bridge=FakeBridge();entered=threading.Event();out=[];bridge.lock.acquire()
  def worker():
   entered.set()
   try:out.append(bridge.call('capture',url='https://fixture.invalid/',captureKey='queued'))
   except RuntimeError as error:out.append(str(error))
  thread=threading.Thread(target=worker);thread.start();entered.wait(1)
  bridge.cancel('queued');bridge.lock.release();thread.join(2)
  self.assertFalse(thread.is_alive());self.assertEqual(bridge.started,0);self.assertIn('取消',out[0])
 def test_cancel_does_not_block_an_unrelated_capture(self):
  bridge=FakeBridge();bridge.cancel('other')
  self.assertEqual(bridge.call('capture',url='https://fixture.invalid/',captureKey='normal'),{'remaining':1})

if __name__=='__main__':unittest.main()
