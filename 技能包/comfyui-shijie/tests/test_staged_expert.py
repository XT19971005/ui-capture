import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from staged_expert import inventory_request,branch_request,merge_stages,read_object
from knowledge_store import load_knowledge

class StagedExpertTests(unittest.TestCase):
 def setUp(self):
  self.rgb=np.zeros((60,100,3),np.uint8);self.k=load_knowledge()
  self.inv=dict(width=100,height=60,knowledge_ack=self.k['receipt'],background_prompt='Clean garden without UI',items=[dict(id='panel',name='纸底板',bucket='containers',parent_id=None,group='面板'),dict(id='label',name='标签',bucket='texts',parent_id='panel',group='面板')])
  self.branches=dict(containers=dict(assets=[dict(id='panel',box=[0,0,100,60],method='edited',prompt='Clean paper without text')]),images=dict(assets=[]),vectors=dict(assets=[]),texts=dict(assets=[dict(id='label',box=[10,10,40,30],method='text',text='Hi',color=[255,255,255])]))
 def merge(self):return merge_stages(self.rgb,self.k,json.dumps(self.inv),**{k:json.dumps(v) for k,v in self.branches.items()})
 def test_inventory_is_small_and_does_not_request_geometry(self):
  s=inventory_request(self.rgb,self.k);self.assertIn('items',s);self.assertIn('不输出坐标',s)
 def test_branch_contains_only_assigned_inventory_and_strict_schema(self):
  s=branch_request(self.rgb,self.k,'texts',json.dumps(self.inv));self.assertIn('label',s);self.assertIn('"method":"text"',s)
 def test_merge_keeps_all_ids_and_parent_cleanup(self):
  p= self.merge();self.assertEqual([r['id'] for r in p['assets']],['panel','label']);self.assertEqual(p['run_policy']['maximum_generation_runs'],1)
 def test_missing_or_duplicate_assets_fail_before_execution(self):
  self.branches['texts']['assets']=[]
  with self.assertRaisesRegex(ValueError,'缺失'):self.merge()
 def test_source_container_with_children_is_rejected(self):
  self.branches['containers']['assets'][0]['method']='source'
  with self.assertRaisesRegex(ValueError,'子层'):self.merge()
 def test_box_is_derived_from_unchanged_path(self):
  self.branches['containers']['assets'][0]['polygon']=[[0,0],[100,0],[100,60],[0,60]]
  self.branches['containers']['assets'][0]['box']=[8,8,92,52]
  p=self.merge();self.assertEqual(p['assets'][0]['box'],[0,0,100,60]);self.assertTrue(p['staged_diagnostics'])
 def test_extra_brace_repair_is_logged_but_missing_quote_not_guessed(self):
  v,changes=read_object('{"assets":[{"id":"a"}}, {"id":"b"}]}');self.assertEqual(len(v['assets']),2);self.assertTrue(changes)
  with self.assertRaises(ValueError):read_object('{"z:5}')
 def test_parent_cycles_rejected(self):
  self.inv['items'][0]['parent_id']='label'
  with self.assertRaisesRegex(ValueError,'循环'):self.merge()
 def test_rebuilt_solid_parent_can_have_separate_child(self):
  self.inv['items'][0]['bucket']='vectors'
  self.branches['containers']['assets']=[]
  self.branches['vectors']['assets']=[dict(id='panel',box=[0,0,100,60],method='solid',color=[100,100,100],ellipse=True)]
  p=self.merge();self.assertEqual(p['assets'][0]['method'],'solid');self.assertEqual(p['assets'][1]['parent_id'],'panel')
 def test_source_parent_remains_rejected_after_geometry_exception(self):
  self.branches['containers']['assets'][0]['method']='source'
  with self.assertRaisesRegex(ValueError,'子层'):self.merge()

if __name__=='__main__':unittest.main()
