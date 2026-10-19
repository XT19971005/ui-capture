import base64,copy,hashlib,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png


class LayerOrderTests(unittest.TestCase):
 def setUp(self):
  self.raw=png(Image.new('RGBA',(40,40),'red'))
  self.scene={'format':'shijie-scene','version':2,'width':40,'height':40,'source':self.raw,'nodes':[{'id':i,'name':i,'type':'rect','x':0,'y':0,'width':20,'height':20,'fill':'#f00','displayMask':{'enabled':False}} for i in ['a','b','c','d']],'groups':[],'edges':[],'recognition':{'reviewStatus':'PASS'},'_partial':True}
 def module(self):
  self.assertIsNotNone(importlib.util.find_spec('layer_order'),'explicit order repair must be implemented')
  import layer_order
  return layer_order
 def relation(self,a,b,confidence=.98):return {'aboveId':a,'belowId':b,'confidence':confidence,'evidence':'原图交叠边缘显示前者遮住后者'}
 def repair(self,relations,uncertain=None,scene=None):
  return self.module().apply_relations(scene or self.scene,{'relations':relations,'uncertain':uncertain or [],'notes':[]})
 def test_reorders_only_nodes_and_invalidates_global_pass(self):
  before=copy.deepcopy(self.scene);result=self.repair([self.relation('a','b')])
  self.assertEqual([n['id'] for n in result['nodes']],['b','a','c','d'])
  self.assertEqual({n['id']:n for n in before['nodes']},{n['id']:n for n in result['nodes']})
  self.assertEqual(self.scene,before);self.assertTrue(result['_partial'])
  self.assertEqual(result['recognition']['orderRepair']['changedIds'],['a','b'])
  self.assertNotEqual(result['recognition']['reviewStatus'],'PASS')
 def test_uncertain_relation_stays_in_original_order(self):
  result=self.repair([self.relation('a','b',.6)], [{'firstId':'c','secondId':'d','reason':'无明确交叠'}])
  self.assertEqual(result['nodes'],self.scene['nodes']);self.assertTrue(result['recognition']['orderRepair']['notes'])
 def test_cycle_and_conflicting_directions_leave_all_order_unchanged(self):
  for relations in ([self.relation('a','b'),self.relation('b','a')],[self.relation('a','b'),self.relation('b','c'),self.relation('c','a')]):
   result=self.repair(relations)
   self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['recognition']['orderRepair']['status'],'NEEDS_REVIEW')
 def test_rejects_unknown_self_duplicate_malformed_and_unsubstantiated_pairs(self):
  for relation in [self.relation('missing','b'),self.relation('a','a'),{**self.relation('a','b'),'confidence':True},{**self.relation('a','b'),'evidence':''},{**self.relation('a','b'),'confidence':float('nan')},{**self.relation('a','b'),'x':1}]:
   with self.subTest(relation=relation),self.assertRaises(ValueError):self.repair([relation])
  with self.assertRaises(ValueError):self.repair([self.relation('a','b')]*2)
 def test_nested_group_children_reorder_without_changing_membership_or_masks(self):
  self.scene['groups']=[{'id':'outer','name':'o','children':['inner','c'],'displayMask':{'enabled':False}},{'id':'inner','name':'i','children':['a','b']}]
  result=self.repair([self.relation('a','b'),self.relation('c','d')])
  self.assertEqual([n['id'] for n in result['nodes']],['d','b','a','c'])
  self.assertEqual(result['groups'][1]['children'],['b','a'])
  self.assertEqual(result['groups'][0],self.scene['groups'][0])
 def test_impossible_group_interleave_is_atomic(self):
  self.scene['groups']=[{'id':'g','name':'g','children':['a','b']}]
  result=self.repair([self.relation('a','c'),self.relation('c','b')])
  self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['groups'],self.scene['groups'])
  self.assertEqual(result['recognition']['orderRepair']['status'],'NEEDS_REVIEW')
 def test_locked_ancestor_and_locked_node_cannot_be_crossed(self):
  for groups in ([],[{'id':'g','name':'g','children':['b'],'locked':True}]):
   scene=copy.deepcopy(self.scene);scene['groups']=groups
   if not groups:scene['nodes'][1]['locked']=True
   result=self.repair([self.relation('a','c')],scene=scene)
   self.assertEqual(result['nodes'],scene['nodes'])
 def test_invalid_ownership_cycles_or_noncontiguous_groups_rejected(self):
  for groups in ([{'id':'g','children':['a','c']}],[{'id':'g','children':['a']},{'id':'h','children':['a']}],[{'id':'g','children':['h']},{'id':'h','children':['g','a']}]):
   scene=copy.deepcopy(self.scene);scene['groups']=groups
   with self.assertRaises(ValueError):self.repair([],scene=scene)
 def test_process_uses_source_once_with_manifest_without_psd_or_generation(self):
  module=self.module();observed={};requests=[]
  def analyze(prompt,images,schema,**kwargs):
   requests.append(prompt)
   observed.update(prompt=prompt,paths=list(images),schema=schema)
   self.assertTrue(all(Path(p).is_file() for p in images))
   return {'relations':[self.relation('a','b')],'uncertain':[],'notes':[]}
  with patch('codex_client.CLIENT.analyze',side_effect=analyze),patch('codex_client.CLIENT.generate',side_effect=AssertionError('order never generates pixels')),patch('subprocess.Popen',side_effect=AssertionError('no PSD exporter')),patch('codex_client.CLIENT.close',return_value=True):
   result=module.process(self.raw,'order',lambda *_:None,lambda:False,original_source=self.raw,resume_scene=self.scene)
  self.assertEqual([n['id'] for n in result['nodes']],['b','a','c','d'])
  self.assertIn('"id": "a"',observed['prompt']);self.assertEqual(len(observed['paths']),1);self.assertEqual(len(requests),1)
  self.assertTrue(all(not Path(p).exists() for p in observed['paths']))
  from session_outputs import SESSIONS
  self.assertIsNone(SESSIONS.get(result['_sessionId'])['psd']);SESSIONS.take(result['_sessionId'])
 def test_source_mismatch_and_cancel_do_not_analyze(self):
  module=self.module();other=png(Image.new('RGBA',(40,40),'blue'))
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',side_effect=AssertionError('invalid source must not analyze')):
   for source,original,cancelled in [(other,other,lambda:False),(self.raw,self.raw,lambda:True)]:
    with self.assertRaises((ValueError,InterruptedError)):module._process(source,'order',lambda *_:None,cancelled,original,Path(tmp),self.scene)
   scene=copy.deepcopy(self.scene);scene['recognition']['sourceOriginalSHA256']='wrong'
   with self.assertRaises(ValueError):module._process(self.raw,'order',lambda *_:None,lambda:False,self.raw,Path(tmp),scene)
 def test_job_route_dispatches_explicit_mode_and_returns_order_report(self):
  import server
  client=server.app.test_client();headers={'X-Shijie-Token':server.TOKEN};base='http://127.0.0.1:19217'
  try:
   with patch.object(server.pool,'submit',side_effect=lambda fn,*a:fn(*a)),patch('codex_client.CLIENT.analyze',return_value={'relations':[self.relation('a','b')],'uncertain':[],'notes':[]}),patch('codex_client.CLIENT.close',return_value=True):
    response=client.post('/jobs',json={'image':self.raw,'original':self.raw,'resume':self.scene,'mode':'repair-order'},headers=headers,base_url=base)
   self.assertEqual(response.status_code,202,response.get_json())
   data=client.get('/jobs/'+response.get_json()['id'],headers=headers,base_url=base).get_json()
   self.assertEqual(data['status'],'completed');self.assertEqual(data['result']['recognition']['orderRepair']['changedIds'],['a','b'])
   self.assertEqual([n['id'] for n in data['result']['nodes']],['b','a','c','d'])
  finally:
   from session_outputs import SESSIONS
   for ident,row in list(server.jobs.items()):
    if row.get('mode')=='repair-order':SESSIONS.take(row.get('sessionId'));server.jobs.pop(ident,None)
 def test_job_route_rejects_missing_scene_before_queuing(self):
  import server
  client=server.app.test_client()
  with patch.object(server.pool,'submit',side_effect=AssertionError('invalid order scene cannot queue')):
   response=client.post('/jobs',json={'image':self.raw,'mode':'repair-order'},headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
  self.assertEqual(response.status_code,400)
 def test_legacy_scene_without_hash_cannot_analyze_unrelated_original(self):
  module=self.module();other=png(Image.new('RGBA',(40,40),'blue'))
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',return_value={'relations':[],'uncertain':[],'notes':[]}):
   with self.assertRaises(ValueError):module._process(self.raw,'order',lambda *_:None,lambda:False,other,Path(tmp),self.scene)
 def test_nonoverlapping_layers_cannot_be_reordered_from_a_claimed_occlusion(self):
  self.scene['nodes'][1]['x']=30
  result=self.repair([self.relation('a','b')])
  self.assertEqual(result['nodes'],self.scene['nodes']);self.assertTrue(result['recognition']['orderRepair']['notes'])
 def test_analysis_failure_or_cancellation_cleans_source_and_publishes_nothing(self):
  module=self.module()
  from session_outputs import SESSIONS
  for cancel_after in (False,True):
   paths=[];state={'cancelled':False};before=SESSIONS.count()
   def analyze(prompt,images,schema,**kwargs):
    paths.extend(images)
    if not cancel_after:raise RuntimeError('offline disconnect')
    state['cancelled']=True
    return {'relations':[self.relation('a','b')],'uncertain':[],'notes':[]}
   with patch('codex_client.CLIENT.analyze',side_effect=analyze),patch('codex_client.CLIENT.close',return_value=True):
    with self.assertRaises((RuntimeError,InterruptedError)):module.process(self.raw,'order',lambda *_:None,lambda:state['cancelled'],resume_scene=self.scene)
   self.assertTrue(paths);self.assertTrue(all(not Path(p).exists() for p in paths));self.assertEqual(SESSIONS.count(),before)
 def test_deleting_completed_order_job_releases_result_but_keeps_original_session(self):
  import server,threading
  from session_outputs import SESSIONS
  original=SESSIONS.put(self.scene,b'original PSD');result=SESSIONS.put(self.scene,None)
  ident='test-completed-order-cleanup';result_id=result['_sessionId'];original_id=original['_sessionId']
  try:
   with patch.dict(server.jobs,{ident:{'status':'completed','mode':'repair-order','sessionId':result_id,'partial':original,'cancel':threading.Event()}}):
    response=server.app.test_client().delete('/jobs/'+ident,headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
    self.assertEqual(response.status_code,200);self.assertNotIn(ident,server.jobs)
    self.assertIsNone(SESSIONS.get(result_id));self.assertEqual(SESSIONS.get(original_id)['psd'],b'original PSD')
    # The already copied scene remains usable after its ephemeral job is removed.
    self.assertEqual(result['nodes'],self.scene['nodes'])
  finally:SESSIONS.take(result_id);SESSIONS.take(original_id)
 def test_deleting_other_completed_jobs_retains_their_download_sessions(self):
  import server,threading
  from session_outputs import SESSIONS
  for mode in ('codex','refine-ui','refine-selected'):
   result=SESSIONS.put(self.scene,b'preserved PSD');session_id=result['_sessionId'];ident='test-other-job-cleanup'
   try:
    with patch.dict(server.jobs,{ident:{'status':'completed','mode':mode,'sessionId':session_id,'cancel':threading.Event()}}):
     response=server.app.test_client().delete('/jobs/'+ident,headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
     self.assertEqual(response.status_code,200);self.assertEqual(SESSIONS.get(session_id)['psd'],b'preserved PSD')
   finally:SESSIONS.take(session_id)
 def test_order_job_delete_tolerates_a_result_session_already_released_by_client(self):
  import server,threading
  from session_outputs import SESSIONS
  result=SESSIONS.put(self.scene,None);ident='test-order-double-release';SESSIONS.take(result['_sessionId'])
  with patch.dict(server.jobs,{ident:{'status':'completed','mode':'repair-order','sessionId':result['_sessionId'],'cancel':threading.Event()}}):
   response=server.app.test_client().delete('/jobs/'+ident,headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
   self.assertEqual(response.status_code,200);self.assertNotIn(ident,server.jobs)

if __name__=='__main__':unittest.main()
