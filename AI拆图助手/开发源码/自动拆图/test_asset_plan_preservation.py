"""Explicit assets never disappear because placement validation skips a row."""
import copy,unittest
from unittest.mock import Mock,patch
from PIL import Image
import engine
from plan_contract import assemble

def plan():
 return {'project_name':'明确资产','assets':[{'id':'item','kind':'person','name':'明确独立主体','box':{'left':10,'top':10,'right':80,'bottom':80},'entity_id':'','parent':None,'z_index':3}],'texts':[],'art_text_ids':[],'text_corrections':[],'vectors':[{'id':'v','name':'矢量','type':'rect','x':1,'y':1,'width':20,'height':20,'fill':'#112233','z_index':1}],'groups':[],'warnings':[]}

class AssetPlanPreservationTests(unittest.TestCase):
 def test_actual_build_rejects_invalid_explicit_assets_instead_of_returning_only_other_layers(self):
  for case in ('negative','out-of-max','malformed-box','empty-id','duplicate-id','boolean'):
   p=plan()
   if case=='negative':p['assets'][0]['box']['left']=-1
   elif case=='out-of-max':p['assets'][0]['box']['right']=101
   elif case=='malformed-box':p['assets'][0]['box']=[10,20,30]
   elif case=='empty-id':p['assets'][0]['id']=''
   elif case=='duplicate-id':p['assets'].append(copy.deepcopy(p['assets'][0]))
   else:p['assets'][0]['box']['left']=True
   with self.subTest(case=case),patch('engine.segment') as segment,self.assertRaises(ValueError):
    engine.build_scene(engine.png(Image.new('RGB',(100,100),'white')),'test',p,lambda *_:None,lambda:False)
   segment.assert_not_called()
 def test_legal_full_canvas_person_and_panel_are_not_removed_by_area(self):
  for kind in ('person','panel'):
   p=plan();p['assets'][0].update(kind=kind,box={'left':0,'top':0,'right':100,'bottom':100})
   with self.subTest(kind=kind):
    scene=engine.build_scene(engine.png(Image.new('RGB',(100,100),'white')),'test',p,lambda *_:None,lambda:False)
    self.assertTrue(any(n.get('sourceAssetId')=='item' for n in scene['nodes']))
 def test_contextual_asset_box_error_is_repairable_without_removing_inventory(self):
  p=plan();p['assets'][0]['box']['left']=-1;before=copy.deepcopy(p);repair=Mock(return_value={'assets':[{'id':'item','box':{'left':10,'top':10,'right':80,'bottom':80}}],'texts':[],'vectors':[],'groups':[],'warnings':[]})
  raw=engine.png(Image.new('RGB',(100,100),'white'))
  result,scene=assemble(p,lambda v:engine.build_scene(raw,'test',v,lambda *_:None,lambda:False),repair,lambda:False,lambda *_:None,canvas_size=(100,100))
  self.assertEqual(repair.call_count,1);self.assertEqual(result['vectors'],before['vectors']);self.assertEqual(len(result['assets']),1);self.assertTrue(any(n.get('sourceAssetId')=='item' for n in scene['nodes']));self.assertEqual(p,before)

if __name__=='__main__':unittest.main()
