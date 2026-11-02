import threading,unittest
import server
class ConcurrencyTests(unittest.TestCase):
 def test_two_jobs_run_concurrently_and_third_waits(self):
  release=threading.Event();started=[threading.Event() for _ in range(3)];futures=[]
  def work(i):
   started[i].set();release.wait(3)
  try:
   futures=[server.pool.submit(work,i) for i in range(3)]
   self.assertTrue(started[0].wait(1))
   self.assertTrue(started[1].wait(1),'second independent job should start before first finishes')
   self.assertFalse(started[2].is_set(),'third job must remain queued')
  finally:
   release.set()
   for f in futures:f.result(5)
  self.assertTrue(started[2].is_set())

 def test_assistant_accepts_second_request_and_bounds_waiting_jobs(self):
  from unittest.mock import patch
  from test_free_assistant import FreeAssistantTests
  body=FreeAssistantTests().body();client=server.app.test_client();kw={'headers':{'X-Shijie-Token':server.TOKEN},'base_url':'http://127.0.0.1:19217'}
  with patch.dict(server.jobs,{'first':{'status':'running'}},clear=True),patch.object(server.pool,'submit'):
   for _ in range(7):self.assertEqual(client.post('/assistant/jobs',json=body,**kw).status_code,202)
   self.assertEqual(client.post('/assistant/jobs',json=body,**kw).status_code,409)

 def test_other_live_turn_does_not_turn_a_completed_task_into_failure(self):
  import importlib
  from unittest.mock import patch
  for name in ['image_replace','codex_pipeline','selected_refine','layer_order']:
   mod=importlib.import_module(name)
   with self.subTest(pipeline=name),patch('session_outputs.run_temporary',side_effect=lambda fn:fn(None)),patch.object(mod,'_process',return_value={'ok':True}),patch('codex_client.CLIENT.close',return_value=False):
    self.assertEqual(mod.process('source','test',lambda *_:None,lambda:False),{'ok':True})
