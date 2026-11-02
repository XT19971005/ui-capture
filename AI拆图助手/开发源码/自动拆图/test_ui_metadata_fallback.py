"""Auxiliary metadata errors cannot discard otherwise valid drawable plans."""
import copy,unittest
from unittest.mock import Mock
from test_ui_components import fixture,build
from plan_contract import assemble
from ui_components import validate_plan,link_scene

class UIAuxiliaryFallbackTests(unittest.TestCase):
 def assert_degraded(self,plan):
  before=copy.deepcopy(plan);builder=Mock(return_value={'nodes':[{'id':'shape','type':'rect','sourceVectorId':'panel'}],'recognition':{}});repair=Mock(side_effect=AssertionError('metadata must not trigger paid reanalysis'))
  returned,scene=assemble(plan,builder,repair,lambda:False,lambda *_:None)
  self.assertEqual(builder.call_count,1);repair.assert_not_called();self.assertEqual(scene['nodes'],[{'id':'shape','type':'rect','sourceVectorId':'panel'}])
  state=scene['recognition']['uiStructure'];self.assertEqual(state['linkStatus'],'NEEDS_REVIEW');self.assertEqual(state['metadataStatus'],'INVALID_METADATA');self.assertEqual(state['components'],[]);self.assertEqual(state['reuseGroups'],[])
  self.assertTrue(state['warnings']);self.assertTrue(returned['warnings']);self.assertEqual(state['invalidMetadata']['uiComponents'],before['uiComponents'])
  for key in ('assets','texts','vectors'):self.assertEqual(returned[key],before[key])
  return scene
 def test_bad_slot_parent_cycle_and_mixed_reuse_degrade_without_repair(self):
  for error in ('slot','cycle','mixed'):
   _,plan=fixture()
   if error=='slot':plan['uiComponents'][1]['slots'][0]['nodeIds']=['absent']
   elif error=='cycle':plan['uiComponents'][1]['parentId']='button-a'
   else:plan['uiReuseGroups'][1]['memberIds']=['label-a','icon-b']
   with self.subTest(error=error):
    with self.assertRaises(ValueError):validate_plan(plan)
    self.assert_degraded(plan)
 def test_valid_metadata_with_unresolvable_scene_references_is_not_marked_resolved(self):
  _,plan=fixture();validate_plan(plan);scene=self.assert_degraded(plan)
  # The actual pipeline links twice. Keep warnings and invalid evidence, never raise.
  link_scene(scene,plan);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA')
  self.assertEqual(len(plan['warnings']),1)
 def test_real_build_survives_bad_auxiliary_metadata(self):
  _,plan=fixture();plan['uiComponents'][1]['slots'][0]['nodeIds']=['absent'];scene=build(plan)
  self.assertEqual(len(scene['nodes']),8);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA')
 def test_actual_pipeline_keeps_warning_and_generates_without_metadata_reanalysis(self):
  import tempfile,codex_pipeline
  from pathlib import Path
  from unittest.mock import patch
  from test_ui_components import native_text
  source,plan=fixture();plan['uiComponents'][1]['slots'][0]['nodeIds']=['absent']
  def asset(work,node,*a,**kw):return {**node,'provenance':'codex-image-generation'}
  def background(work,holder,*a,**kw):holder['nodes'][0]['provenance']='codex-image-generation'
  with tempfile.TemporaryDirectory() as home,patch('engine.text_nodes',side_effect=native_text),patch.object(codex_pipeline.CLIENT,'analyze',return_value=plan) as analysis,patch.object(codex_pipeline.CLIENT,'model',return_value='fixture'),patch('workflow_assets.complete_asset',side_effect=asset) as generated,patch('workflow_assets.complete_background',side_effect=background):
   scene=codex_pipeline._process(source,'重复按钮',lambda *_:None,lambda:False,source,Path(home))
  self.assertEqual(analysis.call_count,1);self.assertEqual(generated.call_count,2);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA')
  self.assertTrue(any('元数据未应用' in warning for warning in scene['recognition']['warnings']))
  self.assertEqual(len(scene['nodes']),8)
 def test_real_geometry_error_still_repaired_and_cannot_be_swallowed(self):
  _,valid=fixture();bad=copy.deepcopy(valid);bad['vectors'][0]['x']=-1;bad['uiComponents'][1]['parentId']='button-a';repairs=[]
  def repair(p,error):repairs.append(error);return copy.deepcopy(valid)
  from test_ui_components import native_text
  import engine
  from unittest.mock import patch
  source,_=fixture()
  with patch('engine.text_nodes',side_effect=native_text):
   _,scene=assemble(bad,lambda p:engine.build_scene(source,'test',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None)
  self.assertEqual(len(repairs),1);self.assertIn('x',repairs[0]);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA')
  repair=Mock(return_value=bad)
  with self.assertRaisesRegex(ValueError,'规划重分析后仍无效'):
   assemble(bad,lambda p:engine.build_scene(source,'test',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None)
  self.assertEqual(repair.call_count,2)
 def test_duplicate_drawable_source_ids_still_repair_instead_of_degrading(self):
  _,plan=fixture();plan['vectors'][0]['id']='icon-a';builder=Mock();repair=Mock(return_value=plan)
  with self.assertRaisesRegex(ValueError,'命名空间'):
   assemble(plan,builder,repair,lambda:False,lambda *_:None)
  builder.assert_not_called();self.assertEqual(repair.call_count,2)

if __name__=='__main__':unittest.main()
