import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from runtime import ROOT
import session_outputs

class LayerReviewIdentityTests(unittest.TestCase):
 def scene(self):
  return {'nodes':[{'id':'a','name':'人物','type':'image','sourceEntityId':'a'},{'id':'b','name':'人物','type':'image','sourceEntityId':'b'},{'id':'button','name':'确认','type':'rect'},{'id':'text','name':'确认','type':'text','text':'确认'},{'id':'path','name':'确认','type':'path','d':'M0 0L5 0L5 5Z'},{'id':'reserved','name':'确认_2','type':'text','text':'原文'}],'recognition':{'reviewStatus':'PASS'}}
 def test_names_are_unique_without_changing_text_entity_or_path(self):
  from layer_review import unique_layer_names
  scene=self.scene();original=copy.deepcopy(scene);unique_layer_names(scene)
  names=[n['name'] for n in scene['nodes']];self.assertEqual(len(names),len(set(names)));self.assertEqual(names[:2],['人物','人物_2']);self.assertEqual(names[2:5],['确认','确认_3','确认_4'])
  for actual,expected in zip(scene['nodes'],original['nodes']):self.assertEqual({k:v for k,v in actual.items() if k!='name'},{k:v for k,v in expected.items() if k!='name'})
  unique_layer_names(scene);self.assertEqual(names,[n['name'] for n in scene['nodes']])
 def test_session_rejects_one_pass_for_duplicate_people(self):
  scene=self.scene();check={'name':'人物','status':'PASS','notes':'synthetic gate record'}
  with tempfile.TemporaryDirectory(dir=ROOT/'依赖/运行临时') as folder:
   qa=Path(folder);(qa/'Codex画面复核.json').write_text(json.dumps({'status':'PASS','asset_checks':[check]}),'utf8');(qa/'画面复核.json').write_text(json.dumps({'checks':[check]}),'utf8')
   scene['nodes']=scene['nodes'][:2]
   with self.assertRaises(ValueError):session_outputs.visual_records(scene,qa)
 def test_each_unique_person_needs_its_own_nonempty_observation(self):
  from layer_review import review_errors,unique_layer_names
  scene=self.scene();scene['nodes']=scene['nodes'][:2];unique_layer_names(scene)
  a={'name':'人物','status':'PASS','notes':'first synthetic observation'};b={'name':'人物_2','status':'PASS','notes':'second synthetic observation'}
  checklist={'checks':[{'name':'人物','status':'PASS','notes':'first file observation','file':'独立图层/001_人物.png'},{'name':'人物_2','status':'PASS','notes':'second file observation','file':'独立图层/002_人物_2.png'}]}
  review={'status':'PASS','asset_checks':[a,b],'file_checks':copy.deepcopy(checklist['checks'])}
  self.assertFalse(review_errors(scene,review,checklist))
  for field in ('asset_checks','file_checks'):
   bad=copy.deepcopy(review);bad[field][1]['notes']='  ';self.assertTrue(review_errors(scene,bad,checklist))
   bad=copy.deepcopy(review);bad[field]=bad[field][:1];self.assertTrue(review_errors(scene,bad,checklist))
   bad=copy.deepcopy(review);bad[field].append(copy.deepcopy(bad[field][0]));self.assertTrue(review_errors(scene,bad,checklist))
 def test_checklist_paths_remain_separate_from_layer_atlas_index(self):
  from layer_review import review_targets,unique_layer_names
  scene=self.scene();unique_layer_names(scene)
  checks=[{'name':n['name'],'file':f'独立图层/{i+1:03d}_{n["name"]}.png'} for i,n in enumerate(scene['nodes'])]
  targets=review_targets(scene,{'checks':checks});self.assertEqual([t['atlasIndex'] for t in targets],list(range(6)));self.assertEqual([t['file'] for t in targets],[c['file'] for c in checks])
 def test_overall_caption_cannot_cover_a_same_name_independent_layer(self):
  from layer_review import unique_check_names,review_targets
  scene={'nodes':[{'name':'完整背景'}]};checklist={'checks':[{'name':'完整背景','file':'03_检查/完整背景.png'},{'name':'完整背景','file':'03_检查/独立图层/001_完整背景.png'}]}
  unique_check_names(scene,checklist);targets=review_targets(scene,checklist)
  self.assertEqual([t['name'] for t in targets],['完整背景_检查2','完整背景']);self.assertEqual([t['atlasIndex'] for t in targets],[None,0])
if __name__=='__main__':unittest.main()
