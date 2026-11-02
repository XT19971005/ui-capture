"""Executable component-instance planning contract, without browsers or generation."""
import copy,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import engine,codex_pipeline
from plan_contract import assemble
from ui_components import validate_plan

def fixture():
 source=engine.png(Image.new('RGB',(160,80),'#f0e4ce'))
 vectors=[{'id':i,'name':i,'type':'rect','x':x,'y':y,'width':w,'height':h,'fill':'#774433','radius':4,'d':'','z_index':z} for i,x,y,w,h,z in [('panel',0,0,160,80,0),('base-a',5,10,60,35,10),('base-b',85,10,60,35,11)]]
 texts=[{'id':i,'text':value,'box':{'left':x,'top':20,'right':x+30,'bottom':35},'z_index':80+n} for n,(i,value,x) in enumerate([('label-a','领取',25),('label-b','已领取',105)])]
 assets=[{'id':i,'name':i,'kind':'icon','entity_id':'','parent':None,'box':{'left':x,'top':20,'right':x+14,'bottom':34},'z_index':40+n} for n,(i,x) in enumerate([('icon-a',8),('icon-b',88)])]
 component=lambda key,state:{'id':'button-'+key,'category':'button','familyId':'reward-button','variant':key,'observedState':state,'parentId':'panel-component','evidence':'实际观察到独立底板、图标与文案','slots':[{'role':'container','nodeIds':['base-'+key]},{'role':'icon','nodeIds':['icon-'+key]},{'role':'label','nodeIds':['label-'+key]}]}
 components=[{'id':'panel-component','category':'panel','familyId':'','variant':'','observedState':'unknown','parentId':None,'evidence':'观察到容纳两个按钮的独立面板','slots':[{'role':'container','nodeIds':['panel']}]},component('a','default'),component('b','disabled')]
 plan={'project_name':'重复按钮','assets':assets,'texts':texts,'vectors':vectors,'groups':[],'warnings':[],'art_text_ids':[],'text_corrections':[],'uiComponents':components,'uiReuseGroups':[{'id':'common-icon','kind':'asset','memberIds':['icon-a','icon-b'],'evidence':'两处图标轮廓和材质相同，仅为复用候选'},{'id':'button-label-style','kind':'text_style','memberIds':['label-a','label-b'],'evidence':'原图文案共用字号、字重与填色，文字内容不同'}]}
 return source,plan

def native_text(rows,rgb,art):
 return ([{'id':'native-'+r['id'],'sourceTextId':r['id'],'name':r['text'],'type':'text','text':r['text'],'x':r['bbox'][0],'y':r['bbox'][1],'width':30,'height':15,'fontFamily':'Arial','fontSize':14,'fontWeight':400,'fill':'#111111'} for r in rows],None)

def build(plan):
 source,_=fixture()
 with patch('engine.text_nodes',side_effect=native_text):
  return assemble(plan,lambda p:engine.build_scene(source,'测试',p,lambda *_:None,lambda:False),lambda p,e:(_ for _ in ()).throw(ValueError(e)),lambda:False,lambda *_:None)[1]

class UIComponentPlanningTests(unittest.TestCase):
 def test_new_model_schema_requires_explicit_component_and_reuse_arrays(self):
  properties=codex_pipeline.PLAN['properties']
  self.assertIn('uiComponents',properties);self.assertIn('uiReuseGroups',properties)
  self.assertIn('uiComponents',codex_pipeline.PLAN['required']);self.assertIn('uiReuseGroups',codex_pipeline.PLAN['required'])
 def test_real_assembly_resolves_slots_and_style_links_to_independent_scene_instances(self):
  _,plan=fixture();scene=build(plan);structure=scene.get('recognition',{}).get('uiStructure')
  self.assertIsNotNone(structure,'component metadata must survive actual plan assembly')
  self.assertEqual(structure['version'],1);self.assertEqual(structure['reuseStatus'],'PLANNED_NOT_APPLIED')
  components={c['id']:c for c in structure['components']};ids={n['id']:n for n in scene['nodes']}
  a=components['button-a'];b=components['button-b'];self.assertEqual(a['parentId'],'panel-component');self.assertEqual(b['observedState'],'disabled')
  a_ids={i for slot in a['slots'] for i in slot['sceneNodeIds']};b_ids={i for slot in b['slots'] for i in slot['sceneNodeIds']};self.assertFalse(a_ids&b_ids)
  labels=[n for n in ids.values() if n.get('sourceTextId')];self.assertEqual({n['text'] for n in labels},{'领取','已领取'});self.assertTrue(all(n['fontSize']==14 and n['fill']=='#111111' for n in labels))
  self.assertEqual(scene['groups'],[],'semantic component containers must not force paint groups')
  links={g['id']:g for g in structure['reuseGroups']};self.assertEqual(set(links['button-label-style']['sceneNodeIds']),{'native-label-a','native-label-b'})
  self.assertEqual(len(links['common-icon']['sceneNodeIds']),2);self.assertTrue(all(i in ids for c in components.values() for slot in c['slots'] for i in slot['sceneNodeIds']))
  self.assertTrue(all(not n.get('locked') for n in ids.values()),'observed disabled state is not an editor lock')
 def test_strict_validator_rejects_unknown_slot_reference(self):
  _,plan=fixture();plan['uiComponents'][1]['slots'][0]['nodeIds']=['does-not-exist']
  with self.assertRaisesRegex(ValueError,'引用|不存在'):
   validate_plan(plan)
 def test_duplicate_slot_ownership_across_instances_is_rejected(self):
  _,plan=fixture();plan['uiComponents'][2]['slots'][2]['nodeIds']=['label-a']
  with self.assertRaisesRegex(ValueError,'重复|归属'):validate_plan(plan)
 def test_parent_cycles_and_unknown_categories_or_states_are_rejected(self):
  for field,value in [('category','imaginary-widget'),('observedState','hover-invented'),('parentId','button-a')]:
   _,plan=fixture();plan['uiComponents'][1][field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):validate_plan(plan)
 def test_text_style_links_cannot_reference_bitmap_or_repeated_members(self):
  for members in (['label-a','icon-b'],['label-a','label-a']):
   _,plan=fixture();plan['uiReuseGroups'][1]['memberIds']=members
   with self.subTest(members=members),self.assertRaises(ValueError):validate_plan(plan)
 def test_two_component_instances_cannot_collapse_into_one_complete_entity(self):
  _,plan=fixture()
  for asset in plan['assets']:asset['entity_id']='wrong-shared-entity'
  scene=build(plan);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA');self.assertEqual(scene['recognition']['uiStructure']['components'],[])
 def test_legacy_plan_without_component_metadata_stays_compatible(self):
  _,plan=fixture();del plan['uiComponents'];del plan['uiReuseGroups'];scene=build(plan)
  self.assertEqual(len(scene['nodes']),8);self.assertNotIn('uiStructure',scene['recognition'])
 def test_empty_component_scan_does_not_invent_controls_on_artwork(self):
  _,plan=fixture();plan['uiComponents']=[];plan['uiReuseGroups']=[];scene=build(plan)
  self.assertEqual(scene['recognition'].get('uiStructure',{}).get('components'),[])
 def test_source_namespaces_cannot_reuse_an_id_between_asset_and_vector(self):
  _,plan=fixture();plan['vectors'][0]['id']='icon-a'
  with self.assertRaisesRegex(ValueError,'命名空间|重复'):build(plan)
 def test_reuse_candidates_cannot_claim_two_members_when_the_scene_has_one_entity(self):
  _,plan=fixture();plan['uiComponents']=[];plan['uiReuseGroups']=plan['uiReuseGroups'][:1]
  for asset in plan['assets']:asset['entity_id']='one-entity'
  scene=build(plan);self.assertEqual(scene['recognition']['uiStructure']['metadataStatus'],'INVALID_METADATA');self.assertEqual(scene['recognition']['uiStructure']['reuseGroups'],[])
 def test_multicolour_art_label_resolves_one_source_to_all_current_ink_paths(self):
  from ui_components import link_scene
  plan={'assets':[{'id':'logo','kind':'logo'}],'texts':[{'id':'art'}],'vectors':[],'art_text_ids':['art'],'uiComponents':[{'id':'mark','category':'unknown','familyId':'','variant':'','observedState':'unknown','parentId':None,'evidence':'观察到多色艺术字，但不足以确认交互类别','slots':[{'role':'label','nodeIds':['art']}]}],'uiReuseGroups':[]}
  node=lambda ident,fill:{'id':ident,'type':'path','fill':fill,'sourceAssetId':'logo','sourceTextParts':['art']}
  scene={'nodes':[node('red','#aa3322'),node('blue','#2233aa'),{**node('archived','#225511'),'versionArchived':True,'visible':False,'hidden':True}]}
  linked=link_scene(scene,plan);slot=linked['recognition']['uiStructure']['components'][0]['slots'][0]
  self.assertEqual(slot['sceneNodeIds'],['red','blue']);self.assertEqual(slot['unresolvedSourceIds'],[])
 def test_first_scan_and_continue_keep_instances_without_extra_paid_diagnosis(self):
  source,plan=fixture();analyses=[];generated=[]
  def analysis(*a,**kw):analyses.append(a[0]);return copy.deepcopy(plan)
  def asset(work,node,*a,**kw):generated.append(node['sourceAssetId']);return {**node,'provenance':'codex-image-generation'}
  def background(work,holder,*a,**kw):holder['nodes'][0]['provenance']='codex-image-generation'
  with tempfile.TemporaryDirectory() as home,patch('engine.text_nodes',side_effect=native_text),patch.object(codex_pipeline.CLIENT,'analyze',side_effect=analysis),patch.object(codex_pipeline.CLIENT,'model',return_value='fixture'),patch('workflow_assets.complete_asset',side_effect=asset),patch('workflow_assets.complete_background',side_effect=background):
   first=codex_pipeline._process(source,'测试',lambda *_:None,lambda:False,source,Path(home))
   edited=copy.deepcopy(first);icon=next(n for n in edited['nodes'] if n.get('sourceAssetId')=='icon-a');edited['nodes'].append({**copy.deepcopy(icon),'id':'history-icon','name':'图标旧版','versionArchived':True,'visible':False,'hidden':True})
   edited['nodes']=[n for n in edited['nodes'] if n.get('sourceTextId')!='label-a'];next(n for n in edited['nodes'] if n.get('sourceTextId')=='label-b')['text']='用户改字'
   continued=codex_pipeline._process(source,'测试',lambda *_:None,lambda:False,source,Path(home),resume_scene=edited)
  self.assertEqual(len(analyses),1,'component metadata must use the single first planning call')
  self.assertIn('uiComponents',analyses[0]);self.assertEqual(generated,['icon-a','icon-b'],'reuse candidates do not silently share generated pixels')
  structure=continued['recognition']['uiStructure'];self.assertEqual(structure['linkStatus'],'PARTIAL');self.assertEqual(structure['reuseStatus'],'PLANNED_NOT_APPLIED')
  a=next(c for c in structure['components'] if c['id']=='button-a');label=next(slot for slot in a['slots'] if slot['role']=='label');self.assertEqual(label['sceneNodeIds'],[]);self.assertEqual(label['unresolvedSourceIds'],['label-a'])
  self.assertNotIn('history-icon',[ident for c in structure['components'] for slot in c['slots'] for ident in slot['sceneNodeIds']]);self.assertTrue(any(n['id']=='history-icon' for n in continued['nodes']))
  self.assertEqual(next(n for n in continued['nodes'] if n.get('sourceTextId')=='label-b')['text'],'用户改字')

if __name__=='__main__':unittest.main()
