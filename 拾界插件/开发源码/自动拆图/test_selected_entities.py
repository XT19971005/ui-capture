"""Controlled model-protocol tests; no paid generation or visual PASS claims."""
import base64,copy,hashlib,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png
import selected_refine

def entity(mode='single-path',members=None,correct=True):
 return {'members':members or ['part-a','part-b','part-c'],'name':'连续字标','kind':'lettermark','mode':mode,'confidence':.99,'evidence':'原图这些颜色区域属于同一组连续书法笔画，不是三个独立物体','contentCorrect':correct,'fill':'#ddbb44','gradient':None,'d':None}

class SelectedEntityTests(unittest.TestCase):
 def setUp(self):
  self.raw=png(Image.new('RGB',(80,60),'#223344'));sha=hashlib.sha256(base64.b64decode(self.raw.split(',')[1])).hexdigest()
  self.parts=[{'id':'part-'+ch,'name':'颜色区'+ch,'type':'path','x':10,'y':10,'width':30,'height':25,'fill':fill,'d':f'M{2+i*7} 2h7v18h-7Z','sourceVectorId':'observed-word'} for i,(ch,fill) in enumerate(zip('abc',['#ddaa22','#ddbb44','#eecc55']))]
  other={'id':'outside','name':'独立物体','type':'rect','x':10,'y':10,'width':30,'height':25,'fill':'#112233'}
  self.scene={'format':'shijie-scene','version':2,'title':'joint','width':80,'height':60,'source':self.raw,'originalSource':self.raw,'comparisonSource':self.raw,'nodes':[other,*self.parts], 'groups':[{'id':'parent','name':'原父组','children':[n['id'] for n in [other,*self.parts]],'displayMask':{'enabled':True,'type':'rect','x':0,'y':0,'width':80,'height':60}}],'edges':[],'recognition':{'sourceOriginalSHA256':sha,'reviewStatus':'NOT_REVIEWED'}}
 def run_selected(self,entities,patches=None,extract=None,region=None,cancelled=lambda:False):
  response={'entities':entities,'patches':patches or [],'assetChecks':[{'id':n['id'],'status':'FAIL','issues':['完整实体被拆成局部']} for n in self.parts if n['type']=='image'],'notes':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',return_value=response) as analyze,patch('incremental_assets.extract_once',side_effect=extract) as generated:
   result=selected_refine._process(self.raw,'joint',lambda *_:None,cancelled,self.raw,Path(tmp),self.scene,[n['id'] for n in self.parts],region=region)
  return result,analyze.call_count,generated.call_count
 def test_three_color_fragments_become_one_complete_native_path_after_joint_visual_decision(self):
  before=copy.deepcopy(self.scene);result,calls,generated=self.run_selected([entity()]);self.assertEqual(calls,1);self.assertEqual(generated,0)
  active=[n for n in result['nodes'] if n['id'] in {p['id'] for p in self.parts} and not n.get('versionArchived')]
  self.assertEqual(len(active),1);self.assertEqual(active[0]['type'],'path');self.assertEqual(active[0]['fill'],'#ddbb44');self.assertGreater(active[0]['d'].count('L')+active[0]['d'].count('H'),0)
  for old in self.parts[1:]:
   retained=next(n for n in result['nodes'] if n['id']==old['id']);self.assertTrue(retained['versionArchived']);self.assertFalse(retained['visible']);self.assertEqual(retained['d'],old['d']);self.assertEqual(retained['fill'],old['fill'])
  self.assertEqual(result['nodes'][0],before['nodes'][0]);self.assertEqual(result['groups'],before['groups']);self.assertEqual(self.scene,before)
  record=result['recognition']['selectedRefine'];self.assertEqual(record['resultSelectedIds'],['part-a']);self.assertEqual(len(record['entityChanges']),1);self.assertNotEqual(record['status'],'PASS')
 def test_same_bounds_without_visual_entity_evidence_never_merges_independent_objects(self):
  result,_,_=self.run_selected([]);self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['groups'],self.scene['groups']);self.assertEqual(result['recognition']['selectedRefine'].get('entityChanges',[]),[])
 def test_multicolor_entity_requires_joint_content_repair_not_just_a_new_group(self):
  result,_,_=self.run_selected([entity('vector-group',correct=False)]);self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['groups'],self.scene['groups']);self.assertEqual(result['recognition']['selectedRefine']['status'],'NEEDS_REVIEW')
 def test_actual_multicolor_group_keeps_original_parent_mask_and_valid_selection(self):
  patches=[{'id':'part-b','changes':{'fill':'#ccaa33'}}];result,_,_=self.run_selected([entity('vector-group',correct=False)],patches);record=result['recognition']['selectedRefine'];group=next(g for g in result['groups'] if g['id'] in record['resultSelectedIds']);self.assertEqual(group['children'],[n['id'] for n in self.parts]);self.assertEqual(result['groups'][0]['displayMask'],self.scene['groups'][0]['displayMask']);self.assertEqual(result['groups'][0]['children'],['outside',group['id']]);self.assertEqual(result['nodes'][0],self.scene['nodes'][0])
 def test_unauthorized_entity_members_are_rejected_without_changing_unselected_objects(self):
  result,_,generated=self.run_selected([entity(members=['part-a','outside'])]);self.assertEqual(generated,0);self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['groups'],self.scene['groups']);self.assertEqual(result['recognition']['selectedRefine']['status'],'NEEDS_REVIEW')
 def image_parts(self):
  for index,n in enumerate(self.parts):
   n.update(type='image',src=png(Image.new('RGBA',(8,8),(20+index,40,60,200))),sourceAssetId='old-'+n['id'],generationRecord={'actualImageGeneration':True,'oldRecord':True})
   n.pop('d');n.pop('fill');n.pop('sourceVectorId')
  self.scene['nodes']=[self.scene['nodes'][0],*self.parts]
 def test_image_fragments_use_one_bounded_complete_entity_extraction_and_keep_old_bytes(self):
  self.image_parts();before=copy.deepcopy(self.scene);seen=[]
  def extract(source,node,*args):
   with Image.open(source) as im:self.assertEqual(im.size,(30,25))
   from asset_geometry import extraction_bounds
   self.assertEqual(extraction_bounds(node),[0,0,30,25]);self.assertTrue(node['_fixedExtractionCanvas'])
   self.assertNotIn('generationRecord',node);self.assertEqual(node['sourceEntityParts'],['old-part-a','old-part-b','old-part-c']);self.assertTrue(node['sourceEntityId'].startswith('selected-entity-'));seen.append(node)
   return {**node,'src':png(Image.new('RGBA',(30,25),'green')),'provenance':'imagegen-complete','generationRecord':{'actualImageGeneration':True}}
  result,calls,generated=self.run_selected([entity('image-union')],extract=extract,region={'x':10,'y':10,'width':30,'height':25})
  self.assertEqual((calls,generated),(1,1));self.assertEqual(result['nodes'][0],before['nodes'][0]);self.assertEqual(result['groups'],before['groups']);self.assertNotEqual(result['nodes'][1]['src'],before['nodes'][1]['src'])
  for i in (2,3):self.assertEqual(result['nodes'][i]['src'],before['nodes'][i]['src']);self.assertEqual(result['nodes'][i]['generationRecord'],before['nodes'][i]['generationRecord']);self.assertTrue(result['nodes'][i]['versionArchived'])
  self.assertEqual(self.scene,before);self.assertEqual(result['recognition']['selectedRefine']['effectiveSelectedIds'],['part-a'])
 def test_image_union_out_of_scope_fails_atomically(self):
  self.image_parts();before=copy.deepcopy(self.scene)
  result,_,calls=self.run_selected([entity('image-union')],extract=lambda source,node,*args:{**node,'x':-1,'provenance':'imagegen-complete'})
  self.assertEqual(calls,1);self.assertEqual(result['nodes'],before['nodes']);self.assertEqual(result['groups'],before['groups']);self.assertEqual(result['recognition']['selectedRefine']['entityChanges'],[])
 def test_entity_failure_restores_partial_native_patches_and_original_bytes(self):
  self.parts[1]['displayMask']={'enabled':True,'type':'rect','x':10,'y':10,'width':10,'height':10};self.scene['nodes'][2]=self.parts[1]
  result,_,_=self.run_selected([entity()],patches=[{'id':'part-a','changes':{'fill':'#ccaa33'}}]);self.assertEqual(result['nodes'],self.scene['nodes']);self.assertEqual(result['groups'],self.scene['groups'])
 def test_cross_parent_noncontiguous_low_evidence_and_text_never_merge(self):
  from selected_entities import eligible
  for change in ('parent','interleaved','confidence','evidence','text'):
   with self.subTest(change=change):
    scene=copy.deepcopy(self.scene);proposal=entity()
    if change=='parent':scene['groups'][0]['children'].remove('part-b')
    elif change=='interleaved':scene['groups'][0]['children']=['part-a','outside','part-b','part-c']
    elif change=='confidence':proposal['confidence']=.89
    elif change=='evidence':proposal['evidence']='同框'
    else:scene['nodes'][1]['type']='text'
    with self.assertRaises(ValueError):eligible(scene,proposal)
 def test_locked_members_fail_before_diagnosis(self):
  self.scene['groups'][0]['locked']=True
  with patch('codex_client.CLIENT.analyze',side_effect=AssertionError('locked selection must not submit')):
   with self.assertRaisesRegex(ValueError,'锁定'):self.run_selected([entity()])
 def test_cancellation_during_joint_extraction_keeps_scene_intact(self):
  self.image_parts();before=copy.deepcopy(self.scene);state={'cancelled':False}
  def extract(source,node,*args):state['cancelled']=True;return {**node,'provenance':'imagegen-complete'}
  with self.assertRaises(InterruptedError):self.run_selected([entity('image-union')],extract=extract,cancelled=lambda:state['cancelled'])
  self.assertEqual(self.scene,before)
 def archive_actual(self,scene):
  script="const fs=require('node:fs'),vm=require('node:vm');const c={window:{},structuredClone,crypto:require('node:crypto')};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),c);const s=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(c.window.ShijieRefinementVersions.archiveChanges(s.before,s.result,s.ids).scene));"
  file=Path(__file__).parents[1]/'工作台增强'/'refinement-versions.js'
  run=subprocess.run([shutil.which('node') or 'node','-e',script,str(file)],input=json.dumps({'before':self.scene,'result':scene,'ids':[n['id'] for n in self.parts]}),capture_output=True,text=True,encoding='utf8',timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if run.returncode:raise AssertionError(run.stderr)
  return json.loads(run.stdout)
 def test_actual_three_joint_corrections_archive_between_members_and_preserve_prior_order(self):
  from layer_order import hierarchy
  for cycle in range(3):
   prior=copy.deepcopy(self.scene);history={n['id']:n for n in prior['nodes'] if n.get('versionArchived')};ids=[n['id'] for n in prior['nodes']]
   result,_,_=self.run_selected([entity('vector-group')]);self.assertEqual(len(result['recognition']['selectedRefine']['entityChanges']),1,cycle)
   self.assertEqual([n['id'] for n in result['nodes']],ids);self.assertEqual({n['id']:n for n in result['nodes'] if n['id'] in history},history)
   archived=self.archive_actual(result);hierarchy(archived)
   self.assertEqual([n['id'] for n in archived['nodes'] if n['id'] in ids],ids);self.assertEqual({n['id']:n for n in archived['nodes'] if n['id'] in history},history);self.assertEqual(sum(bool(n.get('versionArchived')) for n in archived['nodes']),3*(cycle+1))
   self.assertEqual(archived['nodes'][0],self.scene['nodes'][0]);self.assertEqual(archived['groups'][0]['displayMask'],self.scene['groups'][0]['displayMask']);self.scene=archived;self.parts=[n for n in self.scene['nodes'] if n['id'] in {'part-a','part-b','part-c'}]
 def archived_between_members(self):
  first,_,_=self.run_selected([entity('vector-group')]);self.scene=self.archive_actual(first);self.parts=[n for n in self.scene['nodes'] if n['id'] in {'part-a','part-b','part-c'}]
  return next(n for n in self.scene['nodes'] if n.get('versionOf')=='part-b')
 def test_only_explicitly_hidden_history_can_be_ignored_for_adjacency(self):
  from selected_entities import eligible
  archive=self.archived_between_members();before=copy.deepcopy(archive)
  for state in ({'visible':True,'hidden':False},{'visible':True,'hidden':True},{'versionArchived':False},{'versionArchived':False,'visible':True,'hidden':False}):
   with self.subTest(state=state):
    archive.clear();archive.update(copy.deepcopy(before));archive.update(state)
    with self.assertRaisesRegex(ValueError,'交错'):eligible(self.scene,entity('vector-group'))
  archive.clear();archive.update(before);self.assertEqual(len(eligible(self.scene,entity('vector-group'))[0]),3)
 def test_archived_adjacency_does_not_allow_locked_members_or_ancestors(self):
  self.archived_between_members();self.scene['groups'][-1]['locked']=True
  with self.assertRaisesRegex(ValueError,'锁定'):self.run_selected([entity('vector-group')])
 def test_failed_repeat_joint_preserves_all_old_versions_and_current_members(self):
  self.archived_between_members();before=copy.deepcopy(self.scene)
  result,_,_=self.run_selected([entity('vector-group',correct=False)]);self.assertEqual(result['nodes'],before['nodes']);self.assertEqual(result['groups'],before['groups']);self.assertEqual(result['recognition']['selectedRefine']['entityChanges'],[])
 def test_four_native_paths_require_explicitly_empty_image_checks_in_model_schema(self):
  fourth={**self.parts[0],'id':'part-d','fill':'#d5d2b0'};self.parts.append(fourth);self.scene['nodes'].append(fourth);self.scene['groups'][0]['children'].append(fourth['id']);before=copy.deepcopy(self.scene)
  def analyze(prompt,images,schema,*args,**kwargs):
   checks=schema['properties']['assetChecks'];self.assertEqual(checks['minItems'],0);self.assertEqual(checks['maxItems'],0);self.assertIn('assetChecks 必须为 []',prompt)
   return {'entities':[],'patches':[],'assetChecks':[],'notes':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',side_effect=analyze) as model:
   result=selected_refine._process(self.raw,'four-paths',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,[n['id'] for n in self.parts])
  self.assertEqual(model.call_count,1);self.assertEqual(result['nodes'],before['nodes']);self.assertEqual(result['recognition']['selectedRefine']['notes'],[])
 def test_mixed_selection_schema_limits_image_checks_to_exact_image_ids(self):
  self.parts[-1].update(type='image',src=png(Image.new('RGBA',(8,8),'green')));self.parts[-1].pop('d');before=copy.deepcopy(self.scene)
  def analyze(prompt,images,schema,*args,**kwargs):
   checks=schema['properties']['assetChecks'];self.assertEqual(checks['minItems'],1);self.assertEqual(checks['maxItems'],1);self.assertEqual(checks['items']['properties']['id']['enum'],['part-c'])
   return {'entities':[],'patches':[],'assetChecks':[{'id':'part-c','status':'PASS','issues':[]}],'notes':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',side_effect=analyze):result=selected_refine._process(self.raw,'mixed',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,[n['id'] for n in self.parts])
  self.assertEqual(result['recognition']['selectedRefine']['notes'],[]);self.assertEqual(result['nodes'][:3],before['nodes'][:3])
 def test_native_layer_in_image_checks_is_rejected_with_actionable_reason(self):
  reply={'entities':[],'patches':[],'assetChecks':[{'id':'part-a','status':'PASS','issues':[]}],'notes':[]}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',return_value=reply):result=selected_refine._process(self.raw,'path-check',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,[n['id'] for n in self.parts])
  self.assertEqual(result['nodes'],self.scene['nodes']);note=' '.join(result['recognition']['selectedRefine']['notes']);self.assertIn('应有 0 个图片',note);self.assertIn('非图片或未选 ID',note);self.assertEqual(result['recognition']['selectedRefine']['entityChanges'],[])
 def test_missing_duplicate_and_foreign_image_checks_remain_strictly_rejected(self):
  for n in self.parts[1:]:n.update(type='image',src=png(Image.new('RGBA',(8,8),'green')));n.pop('d')
  for ids,reason in ((['part-b'],'遗漏图片 ID'),(['part-b','part-b'],'图片 ID 重复'),(['part-b','outside'],'非图片或未选 ID')):
   with self.subTest(ids=ids),tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',return_value={'entities':[],'patches':[],'assetChecks':[{'id':i,'status':'PASS','issues':[]} for i in ids],'notes':[]}),patch('incremental_assets.extract_once',side_effect=AssertionError('invalid diagnosis must never generate')):
    result=selected_refine._process(self.raw,'invalid-checks',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,[n['id'] for n in self.parts]);self.assertIn(reason,' '.join(result['recognition']['selectedRefine']['notes']));self.assertEqual(result['nodes'][0],self.scene['nodes'][0]);self.assertEqual([n.get('src') for n in result['nodes']],[n.get('src') for n in self.scene['nodes']]);self.assertEqual(result['recognition']['selectedRefine']['entityChanges'],[])

if __name__=='__main__':unittest.main()
