import threading,unittest
from unittest.mock import patch
import server

class CompletionMessageTests(unittest.TestCase):
 def test_incomplete_job_success_does_not_claim_all_assets_completed(self):
  key='completion-message-test'
  server.jobs[key]={'status':'queued','progress':0,'cancel':threading.Event()}
  try:
   with patch('codex_pipeline.process',return_value={'_sessionId':'controlled','_partial':True,'recognition':{'extractionStatus':'INCOMPLETE','pendingGenerationIds':['one','two']}}):
    server.run(key,'source','title','codex','source')
   self.assertEqual(server.jobs[key]['status'],'completed')
   self.assertIn('2',server.jobs[key]['message'])
   self.assertIn('继续拆分',server.jobs[key]['message'])
   self.assertNotIn('拆图完成',server.jobs[key]['message'])
  finally:server.jobs.pop(key,None)
 def test_complete_job_names_completion_explicitly(self):
  key='completion-message-test'
  server.jobs[key]={'status':'queued','progress':0,'cancel':threading.Event()}
  try:
   with patch('codex_pipeline.process',return_value={'_sessionId':'controlled','recognition':{'extractionStatus':'COMPLETED','pendingGenerationIds':[]}}):
    server.run(key,'source','title','codex','source')
   self.assertEqual(server.jobs[key]['message'],'拆分完成')
  finally:server.jobs.pop(key,None)
