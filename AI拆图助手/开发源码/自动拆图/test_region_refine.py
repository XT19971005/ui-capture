"""Bounded region checks must never review or change an unrelated layer."""
import base64, copy, hashlib, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png
import selected_refine


class RegionRefineTests(unittest.TestCase):
 def setUp(self):
  self.raw=png(Image.new('RGBA',(80,60),'red'))
  self.region={'x':10,'y':10,'width':30,'height':30}
  self.node={'id':'actor','name':'角色','type':'image','assetKind':'person','src':png(Image.new('RGBA',(10,10),'blue')),'x':12,'y':12,'width':10,'height':10}
  self.scene={'format':'shijie-scene','version':2,'width':80,'height':60,'source':self.raw,'nodes':[copy.deepcopy(self.node),{**self.node,'id':'outside','x':50},{**self.node,'id':'archive','versionArchived':True,'visible':False,'hidden':True}],'groups':[],'edges':[],'recognition':{'reviewStatus':'NOT_REVIEWED'},'_partial':True}

 def process(self,reply=None,generated=None):
  reply=reply or {'assetChecks':[{'id':'actor','status':'PASS','issues':[]}],'patches':[],'notes':[]}
  captured=[]
  def analyze(prompt,images,schema,*args,**kwargs):
   captured.append((prompt,[Image.open(p).copy() for p in images]))
   return copy.deepcopy(reply)
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',side_effect=analyze),patch('acceptance.review_asset',side_effect=AssertionError('no per-layer re-review')),patch('incremental_assets.check_resume_native',side_effect=AssertionError('no second native review')),patch('incremental_assets.extract_once',return_value=generated) as generation,patch('subprocess.Popen',side_effect=AssertionError('region never exports PSD')):
   result=selected_refine._process(self.raw,'region',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,['actor'],region=self.region)
  return result,captured,generation.call_count

 def test_one_region_diagnostic_uses_actual_crop_and_only_selected_manifest(self):
  result,calls,generated=self.process()
  self.assertEqual(len(calls),1);self.assertEqual(generated,0)
  prompt,images=calls[0]
  self.assertEqual(images[0].size,(30,30));self.assertEqual(images[0].getpixel((0,0))[:3],(255,0,0))
  self.assertIn('"x": 10',prompt);self.assertIn('actor',prompt);self.assertNotIn('outside',prompt);self.assertNotIn('archive',prompt)
  self.assertEqual(result['nodes'][1:],self.scene['nodes'][1:]);self.assertEqual(result['recognition']['selectedRefine']['region'],self.region)
  self.assertTrue(result['_partial']);self.assertNotEqual(result['recognition']['reviewStatus'],'PASS')

 def test_failed_selected_asset_repairs_once_and_archives_are_untouched(self):
  candidate={**self.node,'src':png(Image.new('RGBA',(10,10),'green'))}
  result,calls,count=self.process({'assetChecks':[{'id':'actor','status':'FAIL','issues':['颜色错误']}],'patches':[],'notes':[]},candidate)
  self.assertEqual(count,1);self.assertEqual(result['nodes'][0]['src'],candidate['src']);self.assertEqual(result['nodes'][1:],self.scene['nodes'][1:])
  self.assertTrue(result['recognition']['selectedRefine']['repairedAssetsNotRechecked'])

 def test_invalid_bounds_and_ineligible_nodes_fail_before_model(self):
  cases=[({'x':-1,'y':0,'width':5,'height':5},{}),(dict(self.region,width=0),{}),(dict(self.region,x=70),{}),(dict(self.region,width=float('nan')),{}),(dict(self.region,x=True),{}),(self.region,{'x':39}),(self.region,{'locked':True}),(self.region,{'visible':False}),(self.region,{'hidden':True}),(self.region,{'pendingGeneration':True}),(self.region,{'assetKind':'background'}),(self.region,{'versionArchived':True})]
  for region,changes in cases:
   with self.subTest(region=region,changes=changes):
    scene=copy.deepcopy(self.scene);scene['nodes'][0].update(changes)
    with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',side_effect=AssertionError('must validate before request')):
     with self.assertRaises(ValueError):selected_refine._process(self.raw,'region',lambda *_:None,lambda:False,self.raw,Path(tmp),scene,['actor'],region=region)

 def test_hidden_or_locked_ancestor_rejects_region(self):
  for changes in ({'locked':True},{'visible':False},{'hidden':True},{'versionArchived':True}):
   scene=copy.deepcopy(self.scene);scene['groups']=[{'id':'inner','children':['actor']},{'id':'outer','children':['inner'],**changes}]
   with self.subTest(changes=changes),self.assertRaises(ValueError):selected_refine.validate_selection(scene,['actor'],self.region)

 def test_foreign_diagnostic_id_cannot_repair_or_patch_unselected_node(self):
  reply={'assetChecks':[{'id':'outside','status':'FAIL','issues':['bad']}],'patches':[],'notes':[]}
  result,calls,count=self.process(reply)
  self.assertEqual(count,0);self.assertEqual(result['nodes'][1:],self.scene['nodes'][1:]);self.assertEqual(result['recognition']['selectedRefine']['status'],'NEEDS_REVIEW')

 def test_candidate_that_escapes_region_keeps_original_asset(self):
  candidate={**self.node,'x':50,'src':png(Image.new('RGBA',(10,10),'green'))}
  result,calls,count=self.process({'assetChecks':[{'id':'actor','status':'FAIL','issues':['颜色错误']}],'patches':[],'notes':[]},candidate)
  self.assertEqual(count,1);self.assertEqual(result['nodes'][0]['src'],self.node['src']);self.assertEqual(result['nodes'][0]['x'],12);self.assertEqual(result['recognition']['selectedRefine']['status'],'NEEDS_REVIEW')

 def test_jobs_route_validates_before_queue_and_passes_region(self):
  import server
  body={'image':self.raw,'mode':'refine-selected','resume':self.scene,'selectedIds':['actor'],'region':self.region}
  client=server.app.test_client();headers={'X-Shijie-Token':server.TOKEN};url='http://127.0.0.1:19217'
  with patch.object(server.pool,'submit') as submit:
   response=client.post('/jobs',json={**body,'region':dict(self.region,x=-1)},headers=headers,base_url=url)
   self.assertEqual(response.status_code,400);submit.assert_not_called()
   response=client.post('/jobs',json=body,headers=headers,base_url=url)
   self.assertEqual(response.status_code,202)
   ident=response.json['id']
   try:self.assertEqual(submit.call_args.args[-1],self.region)
   finally:server.jobs.pop(ident,None)

 def test_native_region_patch_keeps_outside_warnings_and_layers_out_of_scope(self):
  self.scene['nodes'][0]={'id':'actor','name':'面板','type':'rect','x':12,'y':12,'width':10,'height':10,'fill':'#112233'}
  self.scene['recognition']['warnings']=['Unrelated old whole-scene warning']
  reply={'assetChecks':[],'patches':[{'id':'actor','changes':{'fill':'#334455'}}],'notes':[]}
  result,calls,count=self.process(reply)
  self.assertEqual(result['nodes'][0]['fill'],'#334455');self.assertEqual(count,0)
  self.assertEqual(result['nodes'][1:],self.scene['nodes'][1:])
  self.assertNotIn('Unrelated old whole-scene warning',result['recognition']['selectedRefine']['notes'])
  self.assertEqual(result['recognition']['warnings'],['Unrelated old whole-scene warning'])

 def test_native_region_patch_moving_outside_roi_is_discarded(self):
  self.scene['nodes'][0]={'id':'actor','name':'面板','type':'rect','x':12,'y':12,'width':10,'height':10,'fill':'#112233'}
  result,calls,count=self.process({'assetChecks':[],'patches':[{'id':'actor','changes':{'x':50}}],'notes':[]})
  self.assertEqual(result['nodes'][0],self.scene['nodes'][0]);self.assertEqual(result['recognition']['selectedRefine']['status'],'NEEDS_REVIEW')


if __name__=='__main__':unittest.main()
