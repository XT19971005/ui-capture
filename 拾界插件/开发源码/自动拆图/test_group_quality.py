import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
import engine, codex_pipeline
from plan_contract import assemble, PlanAssemblyError
from group_quality import validate_planned_groups, mark_group_review, GROUP_PLANNING_RULES


class GroupQualityTests(unittest.TestCase):
 def fixture(self):
  plan={'assets':[],'texts':[],'vectors':[], 'groups':[{'id':'inner','name':'内容','children':['art','caption']},{'id':'outer','name':'区域','children':['inner']}]}
  scene={'nodes':[{'id':'a','sourceAssetId':'art','sourceTextParts':['art-text']},{'id':'b','sourceTextId':'caption'}], 'groups':[{'id':'inner','name':'内容','children':['a','b']},{'id':'outer','name':'区域','children':['inner']}]}
  return plan,scene
 def test_nested_source_aliases_keep_exact_members_without_changing_scene(self):
  plan,scene=self.fixture();plan['groups'][0]['children'].append('art-text');before=copy.deepcopy(scene)
  validate_planned_groups(plan,scene);self.assertEqual(scene,before)
 def test_missing_group_child_or_nested_membership_is_structural_error(self):
  for issue in ('group','child','nesting','unknown'):
   plan,scene=self.fixture()
   if issue=='group':scene['groups'].pop()
   elif issue=='child':scene['groups'][0]['children'].pop()
   elif issue=='nesting':scene['groups'][1]['children']=['a','b']
   else:plan['groups'][0]['children'].append('lost-source')
   with self.subTest(issue=issue),self.assertRaisesRegex(ValueError,'分组结构不完整'):validate_planned_groups(plan,scene)
 def test_assembly_loss_is_not_paid_plan_repair(self):
  plan,scene=self.fixture();scene['groups']=[];repair=Mock()
  with self.assertRaisesRegex(PlanAssemblyError,'分组结构不完整'):assemble(plan,lambda _:scene,repair,lambda:False,lambda *_:None)
  repair.assert_not_called()
 def test_only_automatic_multi_object_flat_scene_gets_visible_warning(self):
  scene={'nodes':[{'id':'bg','assetKind':'background'},{'id':'a'},{'id':'b'}],'groups':[],'recognition':{'automatic':True,'reviewStatus':'NOT_REVIEWED','warnings':['原警告']}}
  before=copy.deepcopy(scene['nodes']);mark_group_review(scene);mark_group_review(scene)
  rec=scene['recognition'];self.assertEqual(rec['groupReviewStatus'],'NEEDS_REVIEW');self.assertEqual(rec['reviewStatus'],'NEEDS_REVIEW')
  self.assertIn(rec['groupReviewIssue'],rec['warnings']);self.assertEqual(rec['warnings'].count(rec['groupReviewIssue']),1)
  self.assertEqual(scene['nodes'],before);self.assertEqual(scene['groups'],[]);self.assertNotIn('delivery',scene)
 def test_manual_flat_scene_and_single_generated_asset_remain_unchanged(self):
  for scene in ({'nodes':[{'id':'a'},{'id':'b'}],'groups':[]}, {'nodes':[{'id':'generated-image'}],'recognition':{'automatic':False}}):
   before=copy.deepcopy(scene);mark_group_review(scene);self.assertEqual(scene,before)
  scene={'nodes':[{'id':'bg','assetKind':'background'},{'id':'asset'}],'recognition':{'automatic':True,'reviewStatus':'NOT_REVIEWED'}}
  mark_group_review(scene);self.assertEqual(scene['recognition']['groupReviewStatus'],'NOT_REQUIRED');self.assertEqual(scene['recognition']['reviewStatus'],'NOT_REVIEWED')
 def test_existing_groups_do_not_claim_semantic_pass(self):
  _,scene=self.fixture();scene['recognition']={'automatic':True,'reviewStatus':'NOT_REVIEWED'}
  mark_group_review(scene);self.assertEqual(scene['recognition']['groupReviewStatus'],'NOT_REVIEWED')
 def test_regrouped_resume_clears_only_its_own_advisory(self):
  scene={'nodes':[{'id':'a'},{'id':'b'}],'groups':[],'recognition':{'automatic':True,'reviewIssue':'原有问题','warnings':['原有问题'],'reviewSummary':'其他检查'}}
  mark_group_review(scene);issue=scene['recognition']['groupReviewIssue'];scene['groups']=[{'id':'g','children':['a','b']}]
  mark_group_review(scene);rec=scene['recognition']
  self.assertEqual(rec['groupReviewStatus'],'NOT_REVIEWED');self.assertEqual(rec['reviewIssue'],'原有问题');self.assertEqual(rec['warnings'],['原有问题']);self.assertNotIn('groupReviewIssue',rec);self.assertNotIn(issue,rec['reviewSummary'])
 def test_real_first_pass_marks_flat_multi_object_without_extra_calls(self):
  raw=engine.png(Image.new('RGB',(24,24),'gray'))
  plan={'project_name':'分组测试','assets':[],'texts':[],'art_text_ids':[],'text_corrections':[],'groups':[],'warnings':[],'vectors':[]}
  nodes=[{'id':i,'name':i,'type':'image','x':0,'y':0,'width':24,'height':24,'src':raw,'assetKind':'background' if i=='bg' else 'icon'} for i in ('bg','a','b')]
  scene={'format':'shijie-scene','version':2,'title':'分组测试','source':raw,'width':24,'height':24,'nodes':nodes,'groups':[],'recognition':{'warnings':[]},'edges':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.model',return_value='test'),patch('codex_pipeline.CLIENT.analyze',return_value=plan) as analysis,patch('engine.build_scene',return_value=scene),patch('workflow_assets.complete_background'),patch('workflow_assets.complete_asset',side_effect=lambda _,n,*a,**kw:{**n,'provenance':'codex-image-generation'}) as generated,patch('acceptance.review_asset',side_effect=AssertionError('no added review')),patch('subprocess.Popen',side_effect=AssertionError('no export')):
   result=codex_pipeline._process(raw,'分组测试',lambda *_:None,lambda:False,raw,Path(tmp))
  self.assertEqual(analysis.call_count,1);self.assertEqual(generated.call_count,2)
  self.assertIn(GROUP_PLANNING_RULES,analysis.call_args.args[0]);self.assertEqual(result['recognition']['groupReviewStatus'],'NEEDS_REVIEW')
  self.assertIn('分组待检查',result['recognition']['reviewSummary']);self.assertNotIn('delivery',result)


if __name__=='__main__':unittest.main()
