import threading, unittest, copy, json
from unittest.mock import patch
import server

class ProgressiveTests(unittest.TestCase):
 def test_snapshot_excludes_placement_proposals_and_is_detached(self):
  from progressive_scene import completed_scene
  scene={'width':100,'height':100,'title':'fixture','source':'source', 'nodes':[
   {'id':'pending','name':'not complete','type':'image','provenance':'pending-image-generation'},
   {'id':'native','name':'fixture native text','type':'text','text':'Hello'},
   {'id':'asset','name':'complete fixture','type':'image','provenance':'codex-image-generation'}],
   'delivery':{'project':'temporary path'},'recognition':{'reviewStatus':'PASS'},'edges':[]}
  snapshot=completed_scene(scene)
  self.assertEqual([n['id'] for n in snapshot['nodes']],['native','asset'])
  self.assertNotIn('delivery',snapshot);self.assertEqual(snapshot['recognition']['reviewStatus'],'NOT_REVIEWED')
  scene['nodes'][1]['text']='changed';self.assertEqual(snapshot['nodes'][0]['text'],'Hello')
 def test_snapshot_preserves_review_needed_but_never_claims_review_is_running_or_passed(self):
  from progressive_scene import completed_scene
  for previous,expected in ((None,'NOT_REVIEWED'),('NOT_REVIEWED','NOT_REVIEWED'),('NEEDS_REVIEW','NEEDS_REVIEW'),('PROCESSING','NOT_REVIEWED'),('PASS','NOT_REVIEWED')):
   scene={'width':20,'height':20,'nodes':[{'id':'done','type':'text','text':'已完成'},{'id':'pending','type':'image','provenance':'pending-image-generation'}],'groups':[],'edges':[],'recognition':{}}
   if previous is not None:scene['recognition']['reviewStatus']=previous
   nodes=copy.deepcopy(scene['nodes']);snapshot=completed_scene(scene)
   with self.subTest(previous=previous):
    self.assertEqual(snapshot['recognition']['reviewStatus'],expected);self.assertEqual(scene['nodes'],nodes);self.assertEqual(snapshot['nodes'],nodes[:1]);self.assertTrue(snapshot['_partial']);self.assertEqual(snapshot['recognition']['pendingGenerationIds'],['pending']);self.assertEqual(snapshot['recognition']['resumePendingNodes'],nodes[1:]);self.assertEqual(scene['recognition'].get('reviewStatus'),previous)
 def test_cancelled_job_json_save_restore_retains_layers_and_pending_without_fake_audit(self):
  from progressive_scene import completed_scene
  from incremental_assets import recover_pending_scene
  for previous in ('NOT_REVIEWED','NEEDS_REVIEW'):
   scene={'width':20,'height':20,'title':'已取消保留','source':'source','nodes':[{'id':'done','type':'text','text':'已完成'},{'id':'pending','type':'image','provenance':'pending-image-generation'}],'groups':[],'edges':[],'recognition':{'reviewStatus':previous}}
   nodes=copy.deepcopy(scene['nodes']);job={'status':'queued','progress':0,'cancel':threading.Event()}
   def process(*a,**kwargs):
    kwargs['on_scene'](completed_scene(scene));job['cancel'].set();raise InterruptedError('cancel after preview')
   with self.subTest(previous=previous),patch.dict(server.jobs,{'cancel-review':job},clear=True),patch('codex_pipeline.process',side_effect=process):
    server.run('cancel-review','source','已取消保留','codex','source')
    response=server.app.test_client().get('/jobs/cancel-review',headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217').get_json()
    self.assertEqual(response['status'],'cancelled');saved=json.loads(json.dumps(response['partial']));self.assertEqual(saved['recognition']['reviewStatus'],previous);self.assertTrue(saved['_partial']);self.assertEqual(saved['recognition']['pendingGenerationIds'],['pending']);self.assertEqual(saved['nodes'],nodes[:1]);self.assertEqual(recover_pending_scene(saved)['nodes'],nodes);self.assertEqual(scene['nodes'],nodes)
 def test_job_publishes_completed_layers_before_finished_without_repeat_payload(self):
  c=server.app.test_client();h={'Host':'127.0.0.1:19217','X-Shijie-Token':server.TOKEN}
  ident='progressive-fixture';server.jobs[ident]={'status':'queued','progress':0,'cancel':threading.Event()}
  def process(*args,**kwargs):
   kwargs['on_scene']({'width':100,'height':100,'nodes':[{'id':'text','type':'text','text':'test-only partial'}]})
   first=c.get('/jobs/'+ident,headers=h).json
   self.assertEqual(first['status'],'running');self.assertEqual(first['partial']['nodes'][0]['text'],'test-only partial')
   revision=first['partialRevision'];same=c.get('/jobs/'+ident+'?afterRevision='+str(revision),headers=h).json
   self.assertNotIn('partial',same)
   return {'_sessionId':'synthetic-not-a-download'}
  try:
   with patch('codex_pipeline.process',side_effect=process):server.run(ident,'source','fixture','codex','source')
   self.assertEqual(server.jobs[ident]['status'],'completed');self.assertNotIn('partial',server.jobs[ident])
  finally:server.jobs.pop(ident,None)

if __name__=='__main__':unittest.main()
