import base64,copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png
import codex_pipeline


class ContinueMissingTests(unittest.TestCase):
 def setUp(self):
  self.source=png(Image.new('RGB',(80,80),'#888888'))
  self.sha=hashlib.sha256(base64.b64decode(self.source.split(',')[1])).hexdigest()
  self.plan={'project_name':'续拆测试','assets':[{'id':key,'entity_id':key,'name':key,'kind':'icon','box':{'left':x,'top':10,'right':x+16,'bottom':26},'parent':None,'z_index':index+20} for index,(key,x) in enumerate([('a',5),('b',30)])],'texts':[],'art_text_ids':[],'text_corrections':[],'vectors':[{'id':'v','name':'底板','type':'rect','x':0,'y':0,'width':70,'height':60,'fill':'#123456','radius':0,'d':'','z_index':10}],'groups':[{'id':'g','name':'角色组','children':['a','b']}],'warnings':[]}
  self.bg={'id':'old-bg','name':'背景','type':'image','assetKind':'background','x':0,'y':0,'width':80,'height':80,'src':self.source,'provenance':'codex-image-generation'}
  self.vector={'id':'old-v','name':'手改底板','type':'rect','sourceVectorId':'v','x':2,'y':3,'width':61,'height':53,'fill':'#abcdef','locked':True}
  self.actor={'id':'old-a','name':'手改角色名','type':'image','assetKind':'icon','sourceAssetId':'a','sourceEntityId':'a','sourceEntityParts':['a'],'x':9,'y':12,'width':25,'height':27,'src':self.source,'provenance':'codex-image-generation','assetReviewStatus':'NEEDS_REVIEW','reviewIssue':'人工待校对，不代表未生成','displayMask':{'enabled':False},'layerStyle':{'outerGlow':{'opacity':.95,'size':90}}}
  self.previous={'format':'shijie-scene','version':2,'title':'用户工程名','width':80,'height':80,'source':self.source,'nodes':[self.bg,self.vector,self.actor],'groups':[{'id':'g','name':'手改组名','children':['old-a'],'opacity':.4,'displayMask':{'enabled':False}}],'edges':[{'from':'old-v','to':'old-a'}],'recognition':{'resumePlan':self.plan,'sourceOriginalSHA256':self.sha,'reviewStatus':'NOT_REVIEWED'},'_partial':True}
 def run_pipeline(self,previous=None,source=None,analysis=None,generate=None,cancelled=lambda:False,previews=None,original=None):
  generated=[];backgrounds=[]
  def asset(work,node,*a,**kw):
   generated.append(copy.deepcopy(node))
   if generate:return generate(node)
   return {**node,'src':self.source,'provenance':'codex-image-generation'}
  def background(work,scene,*a,**kw):
   backgrounds.append(scene['nodes'][0]['id']);scene['nodes'][0]={**scene['nodes'][0],'assetKind':'background','provenance':'codex-image-generation'}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.analyze',side_effect=analysis or AssertionError('continue must not analyze existing content')),patch('codex_pipeline.CLIENT.model',return_value='fixture'),patch('workflow_assets.complete_asset',side_effect=asset),patch('workflow_assets.complete_background',side_effect=background),patch('incremental_assets.check_resume_assets',side_effect=AssertionError('continue may not review old images')),patch('incremental_assets.check_resume_native',side_effect=AssertionError('continue may not review old native nodes')):
   result=codex_pipeline._process(source or self.source,'续拆测试',lambda *_:None,cancelled,original or source or self.source,Path(tmp),on_scene=lambda s:(previews if previews is not None else []).append(copy.deepcopy(s)),resume_scene=previous)
  return result,generated,backgrounds
 def test_continue_generates_only_missing_asset_and_keeps_completed_edits_ids_and_groups(self):
  before=copy.deepcopy(self.previous)
  result,generated,backgrounds=self.run_pipeline(self.previous)
  self.assertEqual([n['sourceAssetId'] for n in generated],['b']);self.assertEqual(backgrounds,[])
  current={n['id']:n for n in result['nodes']}
  for old in before['nodes']:self.assertEqual(current[old['id']],old)
  self.assertEqual(result['edges'],before['edges']);self.assertEqual(result['title'],'用户工程名')
  group=result['groups'][0];self.assertEqual({k:v for k,v in group.items() if k!='children'},{k:v for k,v in before['groups'][0].items() if k!='children'})
  self.assertEqual(group['children'][0],'old-a');self.assertEqual(len(group['children']),2)
  self.assertFalse(result.get('_partial'));self.assertEqual(result['recognition']['pendingGenerationIds'],[])
  self.assertEqual(self.previous,before)
 def test_failed_missing_asset_stays_partial_and_can_be_retried_without_rechecking_complete(self):
  def fail(node):raise RuntimeError('断线')
  partial,generated,_=self.run_pipeline(self.previous,generate=fail)
  self.assertTrue(partial.get('_partial'));self.assertEqual(len(partial['recognition']['pendingGenerationIds']),1)
  self.assertNotIn('已完成',partial['recognition']['reviewSummary'])
  completed,next_generated,_=self.run_pipeline(partial)
  self.assertEqual([n['sourceAssetId'] for n in next_generated],['b']);self.assertFalse(completed.get('_partial'))
  self.assertEqual(next(n for n in completed['nodes'] if n['id']=='old-a'),self.actor)
 def test_interruption_snapshot_recovers_exact_missing_ids_and_never_repeats_finished_calls(self):
  previews=[];calls=[]
  def initial(node):
   calls.append(node['sourceAssetId'])
   if node['sourceAssetId']=='b':raise InterruptedError('取消')
   return {**node,'src':self.source,'provenance':'codex-image-generation'}
  with self.assertRaises(InterruptedError):self.run_pipeline(analysis=lambda *a,**kw:copy.deepcopy(self.plan),generate=initial,previews=previews)
  snapshot=previews[-1];old=copy.deepcopy(snapshot['nodes'])
  self.assertEqual(calls,['a','b'])
  completed,generated,bgs=self.run_pipeline(snapshot)
  self.assertEqual([n['sourceAssetId'] for n in generated],['b']);self.assertEqual(bgs,[])
  self.assertEqual([n['id'] for n in generated],snapshot['recognition']['pendingGenerationIds'])
  self.assertTrue(all(n in completed['nodes'] for n in old));self.assertFalse(completed.get('_partial'))
  self.assertEqual(completed['recognition']['pendingGenerationIds'],[])
 def reject_resume(self,scene,source=None,original=None):
  before=copy.deepcopy(scene)
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.analyze',side_effect=AssertionError('invalid resume must not launch paid planning')),patch('workflow_assets.complete_asset',side_effect=AssertionError('invalid resume must not generate assets')),patch('workflow_assets.complete_background',side_effect=AssertionError('invalid resume must not generate a background')):
   with self.assertRaisesRegex(ValueError,'保留'):
    codex_pipeline._process(source or self.source,'续拆测试',lambda *_:None,lambda:False,original or source or self.source,Path(tmp),resume_scene=scene)
  self.assertEqual(scene,before)
 def test_new_source_with_existing_resume_is_rejected_without_starting_fresh(self):
  other=png(Image.new('RGB',(80,80),'#333333'))
  self.reject_resume(self.previous,source=other)
 def test_changed_working_source_rejected_even_when_original_hash_matches(self):
  other=png(Image.new('RGB',(80,80),'#333333'))
  self.reject_resume(self.previous,source=other,original=self.source)
 def test_missing_or_wrong_original_hash_is_rejected_without_automatic_replanning(self):
  for value in (None,'wrong'):
   scene=copy.deepcopy(self.previous)
   if value is None:scene['recognition'].pop('sourceOriginalSHA256')
   else:scene['recognition']['sourceOriginalSHA256']=value
   with self.subTest(hash=value):self.reject_resume(scene)
 def test_resume_dimensions_and_stored_original_must_match_before_any_paid_call(self):
  for key,value in (('width',81),('height',79),('originalSource',png(Image.new('RGB',(80,80),'#333333')))):
   scene=copy.deepcopy(self.previous);scene[key]=value
   with self.subTest(field=key):self.reject_resume(scene)
 def test_supplied_resume_without_saved_plan_does_not_silently_plan_a_new_project(self):
  scene=copy.deepcopy(self.previous);scene['recognition'].pop('resumePlan')
  self.reject_resume(scene)
 def test_only_an_explicit_fresh_import_without_resume_can_start_new_planning(self):
  other=png(Image.new('RGB',(80,80),'#333333'));analyses=[]
  def analyze(*a,**kw):analyses.append(1);return copy.deepcopy(self.plan)
  result,generated,backgrounds=self.run_pipeline(source=other,analysis=analyze)
  self.assertEqual(len(analyses),1);self.assertEqual(len(backgrounds),1);self.assertEqual([n['sourceAssetId'] for n in generated],['a','b'])
  self.assertNotIn('old-a',[n['id'] for n in result['nodes']])
 def test_locked_pending_asset_is_retained_and_completion_is_not_claimed(self):
  scene=copy.deepcopy(self.previous);scene['nodes'].append({'id':'pending-b','name':'b','type':'image','assetKind':'icon','sourceAssetId':'b','sourceEntityId':'b','sourceEntityParts':['b'],'src':self.source,'x':30,'y':10,'width':16,'height':16,'provenance':'pending-image-generation','locked':True})
  scene['groups'][0]['children'].append('pending-b')
  result,generated,backgrounds=self.run_pipeline(scene)
  self.assertEqual(generated,[]);self.assertEqual(backgrounds,[]);self.assertTrue(result['_partial']);self.assertEqual(result['recognition']['pendingGenerationIds'],['pending-b'])
 def test_explicit_pending_flag_regenerates_only_that_object_and_clears_flag_after_success(self):
  scene=copy.deepcopy(self.previous);scene['nodes'][2]['pendingGeneration']=True
  result,generated,_=self.run_pipeline(scene)
  self.assertEqual([n['sourceAssetId'] for n in generated],['a','b']);self.assertFalse(result.get('_partial'))
  self.assertFalse(next(n for n in result['nodes'] if n['id']=='old-a').get('pendingGeneration'))
 def test_completed_recovery_metadata_does_not_rebuild_or_review_any_object(self):
  from progressive_scene import remember_pending
  scene=copy.deepcopy(self.previous);scene['recognition']['resumePlan']['assets']=scene['recognition']['resumePlan']['assets'][:1]
  scene['recognition']['resumePlan']['groups'][0]['children']=['a'];remember_pending(scene)
  with patch('engine.build_scene',side_effect=AssertionError('completed native nodes must not be rebuilt')):
   result,generated,backgrounds=self.run_pipeline(scene)
  self.assertEqual(generated,[]);self.assertEqual(backgrounds,[]);self.assertEqual(result['nodes'],scene['nodes'])
 def test_nested_partial_groups_keep_locks_and_original_pending_ids(self):
  from progressive_scene import completed_scene
  from incremental_assets import recover_pending_scene,merge_resume_scene
  scene=copy.deepcopy(self.previous);scene['nodes'][2]['provenance']='pending-image-generation';scene['groups']=[{'id':'outer','name':'父组','locked':True,'children':['g']},{'id':'g','name':'子组','children':['old-a']}]
  snapshot=completed_scene(scene)
  self.assertEqual(snapshot['groups'],[])
  recovered=merge_resume_scene(recover_pending_scene(snapshot),snapshot)
  self.assertEqual(recovered['groups'],scene['groups']);self.assertEqual([n['id'] for n in recovered['nodes']],[n['id'] for n in scene['nodes']])
  self.assertEqual(snapshot['recognition']['pendingGenerationIds'],['old-a'])
 def test_all_pending_snapshot_keeps_plan_and_empty_visible_scene_for_recovery(self):
  from progressive_scene import completed_scene
  scene=copy.deepcopy(self.previous);scene['nodes']=[{**self.bg,'provenance':'pending-image-generation'}];scene['groups']=[];scene['edges']=[]
  snapshot=completed_scene(scene)
  self.assertIsNotNone(snapshot);self.assertEqual(snapshot['nodes'],[])
  self.assertEqual(snapshot['recognition']['pendingGenerationIds'],['old-bg']);self.assertEqual(snapshot['recognition']['resumePendingNodes'][0]['id'],'old-bg')
 def test_archived_manual_versions_are_preserved_but_never_counted_or_generated(self):
  scene=copy.deepcopy(self.previous);archive={**copy.deepcopy(self.actor),'id':'archive-a','name':'角色旧版','versionArchived':True,'versionOf':'old-a','visible':False,'hidden':True,'pendingGeneration':True,'provenance':'source-crop-fallback'}
  scene['nodes'].insert(2,archive);scene['groups'][0]['children'].insert(0,'archive-a')
  result,generated,_=self.run_pipeline(scene)
  self.assertEqual([n['sourceAssetId'] for n in generated],['b']);self.assertEqual(next(n for n in result['nodes'] if n['id']=='archive-a'),archive)
  self.assertEqual(result['groups'][0]['children'][:2],['archive-a','old-a']);self.assertEqual(result['recognition']['pendingGenerationIds'],[])
 def test_pending_provenance_on_archived_version_does_not_remove_it_from_snapshot(self):
  from progressive_scene import completed_scene
  scene=copy.deepcopy(self.previous);archive={**copy.deepcopy(self.actor),'id':'archive-a','versionArchived':True,'versionOf':'old-a','visible':False,'hidden':True,'provenance':'pending-image-generation'}
  scene['nodes'].append(archive)
  snapshot=completed_scene(scene)
  self.assertIn(archive,snapshot['nodes']);self.assertEqual(snapshot['recognition']['pendingGenerationIds'],[])
 def test_legacy_resume_does_not_resurrect_a_deleted_completed_native_node(self):
  scene=copy.deepcopy(self.previous);scene['nodes']=[n for n in scene['nodes'] if n['id']!='old-v'];scene['edges']=[]
  result,generated,_=self.run_pipeline(scene)
  self.assertEqual([n['sourceAssetId'] for n in generated],['b']);self.assertFalse(any(n.get('sourceVectorId')=='v' for n in result['nodes']))
 def test_only_missing_new_node_is_renamed_if_user_existing_name_conflicts(self):
  from layer_review import require_unique_names
  scene=copy.deepcopy(self.previous);scene['nodes'][2]['name']='b'
  result,generated,_=self.run_pipeline(scene)
  self.assertEqual(next(n for n in result['nodes'] if n['id']=='old-a')['name'],'b');require_unique_names(result)
  self.assertNotEqual(generated[0]['name'],'b')

if __name__=='__main__':unittest.main()
