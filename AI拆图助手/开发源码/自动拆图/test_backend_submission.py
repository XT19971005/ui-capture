"""Offline lifecycle gaps: no listener, browser or paid model requests."""
import concurrent.futures,copy,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class SubmissionFailureTests(unittest.TestCase):
 def test_simultaneous_submissions_accept_only_one_job(self):
  import server
  image=png(Image.new('RGB',(4,4),'red'));barrier=threading.Barrier(8)
  def submit(_):
   barrier.wait()
   return server.app.test_client().post('/jobs',json={'image':image},headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217').status_code
  with patch.dict(server.jobs,{},clear=True),patch.object(server.pool,'submit'),concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
   codes=list(executor.map(submit,range(8)))
   self.assertEqual(codes.count(202),1);self.assertEqual(codes.count(409),7)
   self.assertEqual(len(server.jobs),1)

 def test_later_pipeline_failure_or_cancel_preserves_latest_completed_preview(self):
  import server,codex_pipeline
  from test_refine_ui import fixture
  source,scene=fixture()
  for error,expected in ((RuntimeError('disconnect'),'failed'),(InterruptedError('cancel'),'cancelled')):
   latest=copy.deepcopy(scene);latest['nodes'][2]['text']='已完成图层'
   def process(*a,**kwargs):kwargs['on_scene'](latest);raise error
   row={'status':'queued','progress':0,'cancel':threading.Event()}
   with self.subTest(status=expected),patch.dict(server.jobs,{'boundary':row},clear=True),patch.object(codex_pipeline,'process',side_effect=process),patch.object(server.logging,'exception'):
    server.run('boundary',source,'fixture','codex',source)
    self.assertEqual(row['status'],expected);self.assertEqual(row['partial'],latest)
    self.assertNotIn('sessionId',row)
    self.assertIn('finished',row)

 def test_executor_rejection_releases_busy_slot_and_accepts_next_job(self):
  import server
  image=png(Image.new('RGB',(4,4),'red'));client=server.app.test_client()
  kwargs={'headers':{'X-Shijie-Token':server.TOKEN},'base_url':'http://127.0.0.1:19217'}
  with patch.dict(server.jobs,{},clear=True),patch.object(server.pool,'submit',side_effect=[RuntimeError('executor unavailable'),None]):
   with patch.object(server.logging,'exception'):
    response=client.post('/jobs',json={'image':image},**kwargs)
   self.assertEqual(dict(server.jobs),{},'rejected dispatch must not keep a permanently queued job')
   self.assertEqual(response.status_code,503)
   self.assertIn('error',response.get_json())
   retry=client.post('/jobs',json={'image':image},**kwargs)
   self.assertEqual(retry.status_code,202,retry.get_json())

class LegacyOriginalTests(unittest.TestCase):
 def setUp(self):
  from test_refine_ui import fixture
  self.source,self.scene=fixture();self.other=png(Image.new('RGB',(180,120),'blue'))
 def test_selected_rejects_unrelated_original_before_review_or_generation(self):
  import selected_refine
  for stored in (False,True):
   with self.subTest(stored=stored),tempfile.TemporaryDirectory() as home:
    scene=copy.deepcopy(self.scene)
    if stored:scene['originalSource']=self.source
    with patch('acceptance.review_asset',return_value={'status':'PASS','issues':[]}):
     with self.assertRaisesRegex(ValueError,'原文件|原图'):selected_refine._process(self.source,'fixture',lambda *_:None,lambda:False,self.other,Path(home),scene,['image'])
 def test_ui_refine_rejects_unrelated_original_before_native_export(self):
  import refine_ui
  for stored in (False,True):
   with self.subTest(stored=stored),tempfile.TemporaryDirectory() as home:
    scene=copy.deepcopy(self.scene)
    if stored:scene['originalSource']=self.source
    with patch.object(refine_ui,'_export',side_effect=AssertionError('unrelated original reached exporter')):
     with self.assertRaisesRegex(ValueError,'原文件|原图'):refine_ui._process(self.source,'fixture',lambda *_:None,lambda:False,self.other,Path(home),scene)

class IncompleteReviewTests(unittest.TestCase):
 def test_incomplete_review_never_regenerates_or_replaces_selected_pixels(self):
  import acceptance,selected_refine
  from test_selected_refine import SelectedRefineTests
  fixture=SelectedRefineTests();fixture.setUp();scene=fixture.scene;source=fixture.raw
  checks=[{'name':name,'status':'PASS','notes':'实际观察'} for name in acceptance.ASSET_CRITERIA]
  incomplete=[{'status':'PASS','checks':[],'issues':[]},
              {'status':'FAIL','checks':checks[:-1]+[checks[0]],'issues':['无法完整检查']},
              {'status':'FAIL','checks':[{**c,'notes':''} for c in checks],'issues':['证据为空']}]
  for response in incomplete:
   replacement={**scene['nodes'][0],'src':png(Image.new('RGBA',(40,40),'blue'))}
   with self.subTest(response=response),tempfile.TemporaryDirectory() as home,patch('acceptance.CLIENT.analyze',return_value=response),patch('incremental_assets.extract_once',return_value=replacement):
    result=selected_refine._process(source,'fixture',lambda *_:None,lambda:False,source,Path(home),scene,['actor'])
    self.assertEqual(result['nodes'][0]['src'],source,'missing observations must preserve the original pixels')
    self.assertEqual(result['recognition']['selectedRefine']['changedIds'],[])
    self.assertEqual(result['nodes'][0]['assetReviewStatus'],'NEEDS_REVIEW')

if __name__=='__main__':unittest.main()
