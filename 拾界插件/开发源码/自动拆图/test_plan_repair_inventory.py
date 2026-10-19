"""Inventory-preserving bounded repairs; controlled local responses, no model calls."""
import copy,unittest
from unittest.mock import Mock,patch
from test_ui_components import fixture,native_text
import engine
from plan_contract import assemble

class RepairInventoryTests(unittest.TestCase):
 def run_partial(self,alter=None):
  source,original=fixture();original['vectors'][1].update(type='path',width=200,d='M5 0L10 10Z');original['groups']=[{'id':'buttons','name':'按钮','children':['base-a','icon-a','label-a','base-b','icon-b','label-b']}]
  # Keep an ungrouped fixture to avoid an independent interleaving-group error.
  original['groups']=[{'id':'first','name':'首个按钮','children':['base-a']}]
  partial={key:[] for key in ('assets','texts','groups','art_text_ids','text_corrections','uiComponents','uiReuseGroups')};partial.update(project_name='不能改工程名',vectors=[{**original['vectors'][1],'width':60,'d':'M0 0L10 10Z','fill':'#ff0000','name':'不应改名','z_index':999}],warnings=['局部修正，空数组不是删除'])
  if alter:alter(partial)
  repair=Mock(return_value=partial)
  with patch('engine.text_nodes',side_effect=native_text):
   plan,scene=assemble(original,lambda p:engine.build_scene(source,'test',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None)
  return original,plan,scene,repair
 def test_partial_empty_arrays_preserve_actual_inventory_and_only_failed_geometry_changes(self):
  before,plan,scene,repair=self.run_partial();self.assertEqual(repair.call_count,1)
  for key in ('assets','texts','groups','art_text_ids','text_corrections','uiComponents','uiReuseGroups','project_name'):self.assertEqual(plan[key],before[key],key)
  self.assertEqual([v['id'] for v in plan['vectors']],[v['id'] for v in before['vectors']]);self.assertEqual(plan['vectors'][0],before['vectors'][0]);self.assertEqual(plan['vectors'][2],before['vectors'][2])
  fixed=plan['vectors'][1];self.assertEqual(fixed['width'],60);self.assertEqual(fixed['d'],'M0 0L10 10Z')
  for key in ('fill','name','z_index'):self.assertEqual(fixed[key],before['vectors'][1][key])
  self.assertEqual(len(scene['nodes']),8);self.assertEqual(scene['recognition']['uiStructure']['linkStatus'],'RESOLVED');self.assertEqual(len(scene['groups']),1)
  self.assertEqual(before['vectors'][1]['width'],200,'do not mutate the original resumable plan')
 def test_auxiliary_repair_reinvention_cannot_block_valid_geometry_or_replace_old_metadata(self):
  def alter(p):p['uiComponents']=[{'id':'unrequested-new-component'}];p['uiReuseGroups']=[{'id':'unrequested-new-reuse'}]
  before,plan,scene,repair=self.run_partial(alter)
  self.assertEqual(repair.call_count,1);self.assertEqual(plan['uiComponents'],before['uiComponents']);self.assertEqual(plan['uiReuseGroups'],before['uiReuseGroups']);self.assertEqual(len(scene['nodes']),8)
 def test_actual_asset_minimum_eight_pixel_and_rounding_repairs_are_not_ignored(self):
  source,valid=fixture()
  for old_right,new_right in ((12,22),(15.4,15.6)):
   before=copy.deepcopy(valid);before['assets'][0]['box']['right']=old_right
   repair_plan={'assets':[{**before['assets'][0],'name':'不能顺带改名','box':{**before['assets'][0]['box'],'right':new_right}}],'texts':[],'vectors':[],'groups':[],'warnings':[]}
   repair=Mock(return_value=repair_plan)
   with self.subTest(old_right=old_right),patch('engine.text_nodes',side_effect=native_text):
    plan,scene=assemble(before,lambda p:engine.build_scene(source,'test',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None,canvas_size=(160,80))
    self.assertEqual(repair.call_count,1);self.assertEqual(plan['assets'][0]['box']['right'],new_right);self.assertEqual(plan['assets'][0]['name'],before['assets'][0]['name']);self.assertEqual(len(scene['nodes']),8)
 def test_repair_addition_or_renaming_is_rejected_without_erasing_inventory(self):
  for change in ('add','rename'):
   def alter(p):
    if change=='add':p['assets']=[{'id':'invented'}]
    else:p['vectors'][0]['id']='renamed'
   with self.subTest(change=change),self.assertRaisesRegex(ValueError,'新增|标识|ID'):self.run_partial(alter)
 def test_repair_with_no_fix_remains_bounded_and_never_builds_tiny_success(self):
  source,plan=fixture();plan['vectors'][1]['width']=200;partial={key:[] for key in ('assets','texts','vectors','groups','uiComponents','uiReuseGroups')};partial['warnings']=[];repair=Mock(return_value=partial)
  with self.assertRaisesRegex(ValueError,'规划重分析后仍无效'):
   assemble(plan,lambda p:engine.build_scene(source,'test',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None)
  self.assertEqual(repair.call_count,2);self.assertEqual(len(plan['assets']),2);self.assertEqual(len(plan['vectors']),3)

 def test_failed_repair_publishes_inventory_draft_then_explicit_continue_repairs_without_rescan(self):
  import tempfile,codex_pipeline
  from pathlib import Path
  source,valid=fixture();bad=copy.deepcopy(valid);bad['vectors'][1]['width']=200
  empty={key:[] for key in ('assets','texts','vectors','groups','uiComponents','uiReuseGroups')};empty['warnings']=['局部修正不是删除']
  snapshots=[]
  def asset(work,node,*a,**kw):return {**node,'provenance':'codex-image-generation'}
  def background(work,holder,*a,**kw):holder['nodes'][0]['provenance']='codex-image-generation'
  with tempfile.TemporaryDirectory() as home,patch('engine.text_nodes',side_effect=native_text),patch.object(codex_pipeline.CLIENT,'analyze',side_effect=[bad,empty,empty]) as analyze,patch('workflow_assets.complete_asset',side_effect=asset) as generated,patch('workflow_assets.complete_background',side_effect=background) as backgrounds:
   with self.assertRaisesRegex(ValueError,'规划重分析后仍无效'):
    codex_pipeline._process(source,'重复按钮',lambda *_:None,lambda:False,source,Path(home),snapshots.append)
   self.assertEqual(analyze.call_count,3);generated.assert_not_called();backgrounds.assert_not_called()
   self.assertTrue(snapshots);draft=snapshots[-1];self.assertTrue(draft['_partial']);self.assertEqual(draft['recognition']['planningStatus'],'FAILED');self.assertEqual(draft['recognition']['extractionStatus'],'INCOMPLETE')
   for key in ('assets','texts','vectors','groups','uiComponents','uiReuseGroups'):self.assertEqual(draft['recognition']['resumePlan'][key],bad[key])
  with tempfile.TemporaryDirectory() as home,patch('engine.text_nodes',side_effect=native_text),patch.object(codex_pipeline.CLIENT,'analyze',return_value=valid) as analyze,patch.object(codex_pipeline.CLIENT,'model',return_value='fixture'),patch('workflow_assets.complete_asset',side_effect=asset) as generated,patch('workflow_assets.complete_background',side_effect=background):
   result=codex_pipeline._process(source,'重复按钮',lambda *_:None,lambda:False,source,Path(home),resume_scene=draft)
  self.assertEqual(analyze.call_count,1,'resume repairs saved inventory rather than repeating first scan');self.assertEqual(generated.call_count,2);self.assertEqual(len(result['nodes']),8);self.assertEqual(result['recognition']['extractionStatus'],'COMPLETED')

 def test_user_edited_failed_planning_draft_never_rebuilds_over_user_nodes(self):
  import tempfile,codex_pipeline
  from pathlib import Path
  source,valid=fixture();bad=copy.deepcopy(valid);bad['vectors'][1]['width']=200;snapshots=[]
  empty={key:[] for key in ('assets','texts','vectors','groups')};empty['warnings']=[]
  with tempfile.TemporaryDirectory() as home,patch.object(codex_pipeline.CLIENT,'analyze',side_effect=[bad,empty,empty]):
   with self.assertRaises(ValueError):codex_pipeline._process(source,'重复按钮',lambda *_:None,lambda:False,source,Path(home),snapshots.append)
  edited=copy.deepcopy(snapshots[-1]);edited['nodes'].append({'id':'manual','name':'用户新建','type':'rect','x':1,'y':1,'width':10,'height':10,'fill':'#112233'});before=copy.deepcopy(edited)
  with tempfile.TemporaryDirectory() as home,patch.object(codex_pipeline.CLIENT,'analyze',return_value=valid) as analyze,patch('workflow_assets.complete_asset') as generated,patch('workflow_assets.complete_background') as background:
   with self.assertRaisesRegex(ValueError,'草稿.*编辑'):
    codex_pipeline._process(source,'重复按钮',lambda *_:None,lambda:False,source,Path(home),resume_scene=edited)
   analyze.assert_not_called();generated.assert_not_called();background.assert_not_called()
  self.assertEqual(edited,before)

if __name__=='__main__':unittest.main()
