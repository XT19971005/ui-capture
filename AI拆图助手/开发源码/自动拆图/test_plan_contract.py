import unittest,json
from unittest.mock import patch
from PIL import Image
import engine,codex_pipeline

class PlanContractTests(unittest.TestCase):
 def test_real_pipeline_repairs_bad_text_box_before_generation(self):
  import tempfile,copy
  from pathlib import Path
  raw=engine.png(Image.new('RGB',(100,100),'white'))
  valid={'project_name':'测试','assets':[],'texts':[],'art_text_ids':[],'text_corrections':[],'groups':[],'warnings':[],'vectors':[{'id':'v','name':'底板','type':'rect','x':0,'y':0,'width':30,'height':30,'fill':'#000000','radius':0,'d':''}]}
  valid['texts']=[{'id':'t','text':'字','box':{'left':0,'top':0,'right':10,'bottom':10}}];bad=copy.deepcopy(valid);bad['texts'][0]['box']['left']=-2
  class ReachedValidGeneration(Exception):pass
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.analyze',side_effect=[bad,valid]) as analysis,patch('workflow_assets.complete_background',side_effect=ReachedValidGeneration) as generated:
   with self.assertRaises(ReachedValidGeneration):codex_pipeline._process(raw,'测试',lambda *_:None,lambda:False,raw,Path(tmp))
   self.assertEqual(analysis.call_count,2);generated.assert_called_once()
 def test_fill_schema_rejects_unimplemented_values(self):
  self.assertEqual(codex_pipeline.PLAN['properties']['vectors']['items']['properties']['fill']['pattern'],'^#[0-9a-fA-F]{6}$')
 def test_invalid_vector_reports_exact_layer_and_field_before_work(self):
  raw=engine.png(Image.new('RGB',(100,100),'white'))
  plan={'assets':[],'texts':[],'vectors':[{'id':'ring','name':'空心环','type':'ellipse','x':10,'y':10,'width':30,'height':30,'fill':'none'}]}
  with patch('engine.text_nodes') as text,patch('engine.segment') as segment:
   with self.assertRaisesRegex(ValueError,'空心环.*fill'):engine.build_scene(raw,'测试',plan,lambda *_:None,lambda:False)
  text.assert_not_called();segment.assert_not_called()
 def test_lossless_short_hex_expansion_and_path_semantics(self):
  from plan_contract import vector
  v={'id':'shape','name':'形状','type':'rect','x':0,'y':0,'width':20,'height':20,'fill':'#aB3','radius':0}
  self.assertEqual(vector(v,100,100,0)['fill'],'#aabb33')
  for d in ['M','M0 0L','M0 0H1e999']:
   with self.assertRaisesRegex(ValueError,'shape.*d'):vector({**v,'type':'path','d':d},100,100,0)
  with self.assertRaisesRegex(ValueError,'shape.*radius'):vector({**v,'radius':10000},100,100,0)
 def test_art_text_alias_and_normal_cost_remain_in_group(self):
  raw=engine.png(Image.new('RGB',(100,100),'white'))
  text=lambda ident,value,x:{'id':ident,'text':value,'box':{'left':x,'top':10,'right':x+10,'bottom':30}}
  plan={'assets':[{'id':'logo','kind':'logo','name':'完整艺术字','box':[0,0,50,40]},{'id':'person','kind':'person','name':'人物','box':[55,0,95,80]}],'texts':[text('art','字',5),text('cost','10',60)],'art_text_ids':['art'],'vectors':[],'groups':[{'id':'group','name':'父组','children':['logo','art','person','cost']}]}
  proposals=[{'id':a['id'],'name':a['name'],'kind':a['kind'],'box':a['box'],'sourceTextParts':a.get('sourceTextParts',[]),'mask':__import__('numpy').ones((100,100),dtype='uint8'),'pendingGeneration':True} for a in plan['assets']]
  def segmented(rgb,assets,*args,**kwargs):
   for row in proposals:row['sourceTextParts']=next(a.get('sourceTextParts',[]) for a in assets if a['id']==row['id'])
   return proposals
  def fitted(rows,rgb,art):return ([{'id':'cost-node','name':'10','text':'10','type':'text','sourceTextId':'cost','x':60,'y':10,'width':10,'height':20,'fill':'#ffffff'}] if 'cost' not in art else []),None
  with patch('engine.segment',side_effect=segmented),patch('engine.text_nodes',side_effect=fitted):scene=engine.build_scene(raw,'图',plan,lambda *_:None,lambda:False)
  self.assertTrue(any(n.get('sourceTextId')=='cost' for n in scene['nodes']))
  self.assertEqual(next(n for n in scene['nodes'] if n.get('sourceAssetId')=='logo')['sourceTextParts'],['art'])
  self.assertEqual(len(scene['groups'][0]['children']),3)

if __name__=='__main__':unittest.main()
