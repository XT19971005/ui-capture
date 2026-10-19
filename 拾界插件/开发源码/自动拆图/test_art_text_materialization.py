"""Explicit art-text evidence may supply its missing asset representation locally."""
import copy,unittest,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
import engine,codex_pipeline
from plan_contract import assemble,PlanAssemblyError

def fixture():
 image=Image.new('RGB',(140,80),'#eee2cc');draw=ImageDraw.Draw(image)
 for x in (20,45,70):draw.rectangle((x,20,x+10,48),fill='#992233')
 raw=engine.png(image)
 text={'id':'word','text':'研究所','box':{'left':18,'top':18,'right':84,'bottom':52},'z_index':27,'gradient':None,'layerStyle':None,'displayMask':None}
 plan={'project_name':'艺术字','assets':[],'texts':[text],'vectors':[],'art_text_ids':['word'],'text_corrections':[],'warnings':[],'groups':[{'id':'title','name':'标题','children':['word']}],'uiComponents':[{'id':'unknown-mark','category':'unknown','familyId':'','variant':'','observedState':'unknown','parentId':None,'evidence':'观察到原图艺术字，但没有交互证据','slots':[{'role':'label','nodeIds':['word']}]}],'uiReuseGroups':[]}
 return raw,plan

class ArtTextMaterializationTests(unittest.TestCase):
 def test_actual_assembly_creates_missing_complete_logo_without_reanalysis_or_plain_font(self):
  raw,original=fixture();before=copy.deepcopy(original);repair=Mock(side_effect=AssertionError('no extra paid analysis'))
  plan,scene=assemble(original,lambda p:engine.build_scene(raw,'艺术字',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None,canvas_size=(140,80))
  repair.assert_not_called();self.assertEqual(original,before);self.assertEqual(plan['texts'],before['texts']);self.assertEqual(plan['groups'],before['groups']);self.assertEqual(len(plan['assets']),1)
  asset=plan['assets'][0];self.assertEqual(asset['kind'],'logo');self.assertEqual(asset['box'],original['texts'][0]['box']);self.assertEqual(asset['z_index'],27);self.assertEqual(asset['sourceTextParts'],['word']);self.assertFalse(asset['entity_id'])
  self.assertFalse(any(n['type']=='text' for n in scene['nodes']));art=[n for n in scene['nodes'] if n.get('sourceTextParts')==['word']];self.assertTrue(art);self.assertTrue(all(n['z_index']==27 for n in art))
  slot=scene['recognition']['uiStructure']['components'][0]['slots'][0];self.assertEqual(set(slot['sceneNodeIds']),{n['id'] for n in art});self.assertEqual(set(scene['groups'][0]['children']),set(slot['sceneNodeIds']))
 def test_existing_logo_and_ordinary_text_never_gain_a_duplicate_asset(self):
  from plan_contract import complete_art_text_assets
  _,plan=fixture();plan['assets']=[{'id':'existing','name':'既有完整字标','kind':'logo','box':{'left':15,'top':15,'right':86,'bottom':54},'parent':None,'entity_id':'','z_index':27}]
  self.assertEqual(complete_art_text_assets(plan,(140,80)),plan)
  _,ordinary=fixture();ordinary['art_text_ids']=[];self.assertEqual(complete_art_text_assets(ordinary,(140,80)),ordinary)
 def test_distinct_observed_art_instances_stay_distinct_and_completion_is_idempotent(self):
  from plan_contract import complete_art_text_assets
  _,plan=fixture();second=copy.deepcopy(plan['texts'][0]);second.update(id='second',box={'left':90,'top':20,'right':130,'bottom':55},z_index=28);plan['texts'].append(second);plan['art_text_ids'].append('second')
  completed=complete_art_text_assets(plan,(140,80));self.assertEqual(len(completed['assets']),2);self.assertEqual(len({a['id'] for a in completed['assets']}),2);self.assertEqual([a['sourceTextParts'] for a in completed['assets']],[['word'],['second']]);self.assertTrue(all(not a['entity_id'] for a in completed['assets']));self.assertEqual(complete_art_text_assets(completed,(140,80)),completed)
 def test_synthesized_representation_never_swallows_another_explicit_art_id(self):
  import planner,json
  from plan_contract import complete_art_text_assets,link_art_text
  _,plan=fixture();second=copy.deepcopy(plan['texts'][0]);second.update(id='second',box={'left':20,'top':18,'right':84,'bottom':52});plan['texts'].append(second);plan['art_text_ids'].append('second')
  completed=complete_art_text_assets(plan,(140,80));self.assertEqual(len(completed['assets']),2)
  normalized=planner.parse_plan(json.dumps(completed),140,80,(140,80));rows=engine.text_rows(completed,140,80);link_art_text(normalized['assets'],rows,set(plan['art_text_ids']))
  self.assertEqual({a['derivedFromArtTextId']:a['sourceTextParts'] for a in normalized['assets']},{'word':['word'],'second':['second']})
 def test_unknown_or_too_small_art_evidence_never_turns_into_ordinary_font_or_paid_retry(self):
  for error in ('unknown','small'):
   raw,plan=fixture()
   if error=='unknown':plan['art_text_ids']=['absent']
   else:plan['texts'][0]['box']['right']=22
   repair=Mock(side_effect=AssertionError('deterministic missing representation is not a paid repair'))
   with self.subTest(error=error),self.assertRaises(PlanAssemblyError):
    assemble(plan,lambda p:engine.build_scene(raw,'艺术字',p,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None,canvas_size=(140,80))
   repair.assert_not_called()
 def test_actual_pipeline_uses_only_initial_analyze_then_keeps_source_text_association(self):
  raw,plan=fixture()
  def background(work,holder,*a,**kw):holder['nodes'][0]['provenance']='codex-image-generation'
  with tempfile.TemporaryDirectory() as home,patch.object(codex_pipeline.CLIENT,'analyze',return_value=plan) as analyze,patch.object(codex_pipeline.CLIENT,'model',return_value='fixture'),patch('workflow_assets.complete_background',side_effect=background):
   scene=codex_pipeline._process(raw,'艺术字',lambda *_:None,lambda:False,raw,Path(home))
  self.assertEqual(analyze.call_count,1);self.assertEqual(len(scene['recognition']['resumePlan']['assets']),1);self.assertTrue(any(n.get('sourceTextParts')==['word'] for n in scene['nodes']));self.assertEqual(scene['recognition']['extractionStatus'],'COMPLETED')

if __name__=='__main__':unittest.main()
