import copy,unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import engine,planner,codex_pipeline,workflow_assets

GRAD={'kind':'radial','angle':35,'scale':.8,'stops':[[0,'#ff9900'],[1,'#2255ff']]}
STYLE={'enabled':True,'blendMode':'screen','dropShadow':{'enabled':True,'color':'#000000','size':12,'opacity':.4,'angle':120,'distance':8}}
MASK={'enabled':True,'type':'rect','x':10,'y':12,'width':50,'height':40}
class DesignPlanningTests(unittest.TestCase):
 def test_structured_plan_has_real_gradient_style_and_group_mask_fields(self):
  props=codex_pipeline.PLAN['properties']
  for field in ['assets','texts','vectors']:
   child=props[field]['items']['properties']
   self.assertIn('layerStyle',child);self.assertIn('displayMask',child)
  self.assertIn('gradient',props['vectors']['items']['properties']);self.assertIn('groups',props)
 def test_invalid_visual_properties_do_not_silently_drop(self):
  from design_properties import design_fields
  for value in [{'gradient':{**GRAD,'scale':0}},{'gradient':{**GRAD,'stops':[[1,'#ff9900'],[0,'#2255ff']]}},{'layerStyle':{**STYLE,'dropShadow':{**STYLE['dropShadow'],'size':float('nan')}}},{'displayMask':{**MASK,'width':0}},*[{'displayMask':{**MASK,'type':'path','d':d}} for d in ['<script>','M','M0 0L','M0 0H1e999']]]:
   with self.subTest(value=value),self.assertRaises(ValueError):design_fields(value)
 def test_build_scene_resolves_plan_ids_and_keeps_text_gradient(self):
  source=engine.png(Image.new('RGB',(100,80),'white'))
  plan={'assets':[{'id':'icon','entity_id':'','name':'图标','kind':'decoration','box':{'left':10,'top':10,'right':30,'bottom':30},'parent':None,'layerStyle':STYLE}],
   'texts':[{'id':'text','text':'TEST','box':{'left':40,'top':10,'right':80,'bottom':30},'gradient':GRAD}],
   'vectors':[{'id':'panel','name':'底板','type':'rect','x':10,'y':40,'width':60,'height':20,'fill':'#ff9900','radius':0,'d':'','gradient':GRAD,'layerStyle':STYLE}],
   'groups':[{'id':'parent','name':'内容组','children':['icon','text','panel'],'displayMask':MASK,'layerStyle':STYLE}]}
  text={'id':'real-text','name':'TEST','type':'text','text':'TEST','x':40,'y':10,'width':40,'height':20,'fontSize':16,'fill':'#000000','sourceTextId':'text'}
  with patch('engine.text_nodes',return_value=([text],None)):
   scene=engine.build_scene(source,'TEST',plan,lambda *_:None,lambda:False)
  group=scene['groups'][0];nodes={n['id']:n for n in scene['nodes']}
  self.assertEqual(group['displayMask'],MASK);self.assertEqual(len(group['children']),3)
  self.assertTrue(all(i in nodes for i in group['children']))
  self.assertEqual(nodes['real-text']['gradient'],GRAD)
  panel=next(n for n in nodes.values() if n.get('sourceVectorId')=='panel')
  self.assertEqual(panel['gradient'],GRAD);self.assertEqual(panel['layerStyle'],STYLE)
  icon=next(n for n in nodes.values() if n.get('sourceAssetId')=='icon')
  self.assertEqual(icon['layerStyle'],STYLE)
 def test_unknown_group_members_and_duplicate_ownership_are_rejected(self):
  from design_properties import attach_groups
  s={'nodes':[{'id':'a','name':'a','sourceAssetId':'a'}],'groups':[]}
  for groups in [[{'id':'g','name':'g','children':['missing']}],[{'id':'g','name':'g','children':['a']},{'id':'g2','name':'g2','children':['a']}]]:
   with self.assertRaises(ValueError):attach_groups(copy.deepcopy(s),groups)
 def test_complete_asset_does_not_drop_style_or_bake_shadow(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);src=p/'source.png';Image.new('RGB',(100,80),'white').save(src)
   assets=p/'assets';structure=p/'structure';assets.mkdir();structure.mkdir()
   node={'id':'asset','name':'图标','type':'image','assetKind':'decoration','x':10,'y':10,'width':30,'height':30,'layerStyle':STYLE,'displayMask':MASK}
   def generate(prompt,images,target,**kwargs):
    self.assertIn('不',prompt);Image.new('RGBA',(46,46),(255,120,50,255)).save(target)
    return {'actualImageGeneration':True,'transparent':True,'file':str(target)}
   with patch('workflow_assets.reusable_complete_asset',return_value=None),patch('workflow_assets.CLIENT.generate',side_effect=generate) as gen:
    result=workflow_assets.complete_asset(src,node,assets,structure,lambda:False)
   self.assertEqual(result['layerStyle'],STYLE);self.assertEqual(result['displayMask'],MASK)
   self.assertIn('图层样式',gen.call_args.args[0])
 def test_parent_checks_are_bound_and_sent_to_vision(self):
  import hashlib
  with tempfile.TemporaryDirectory() as tmp:
   qa=Path(tmp)/'03_检查';folder=qa/'父组显示检查';folder.mkdir(parents=True)
   f=folder/'on.png';Image.new('RGBA',(8,8),(255,0,0,255)).save(f)
   proof={'psdSHA256':'actual-psd','groups':[{'name':'父组','files':{'enabled':{'file':'父组显示检查/on.png','sha256':hashlib.sha256(f.read_bytes()).hexdigest()}}}]}
   (qa/'独立回读图层来源.json').write_text(json.dumps(proof),'utf8');checks={'psdSHA256':'actual-psd','checks':[]}
   workflow_assets.append_group_checks(qa,checks)
   self.assertEqual(workflow_assets.review_reference_files(qa,checks),[f.resolve()])
   f.write_bytes(b'changed')
   with self.assertRaises(ValueError):workflow_assets.append_group_checks(qa,checks)
 def test_second_round_asset_reuse_keeps_current_id_and_style(self):
  prior={'id':'old','name':'old','src':'same-complete-bytes','x':2,'y':2,'width':50,'height':50,'gradient':GRAD,'layerStyle':STYLE}
  current={'id':'new','name':'new','x':10,'y':10,'width':30,'height':30,'sourceAssetId':'icon','layerStyle':{**STYLE,'dropShadow':{**STYLE['dropShadow'],'size':15}}}
  reused=workflow_assets.reuse_current_asset(prior,current)
  self.assertEqual(reused['id'],'new');self.assertEqual(reused['layerStyle']['dropShadow']['size'],15)
  self.assertEqual(reused['src'],prior['src']);self.assertEqual(reused['width'],50);self.assertNotIn('gradient',reused)
if __name__=='__main__':unittest.main()
