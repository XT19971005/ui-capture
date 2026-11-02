"""Foreground planning contracts and actual local assembly; no paid calls."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import engine,codex_pipeline,workflow_assets

class Captured(Exception):pass

def fixture():
 raw=engine.png(Image.new('RGB',(160,120),'#8877aa'))
 rear={'id':'rear','name':'后层装饰','type':'path','x':0,'y':30,'width':160,'height':90,'fill':'#9b673e','radius':0,'d':'M0 30Q40 0 80 30T160 30V90H0Z','z_index':10}
 plane={'id':'plane','name':'独立前景面','type':'path','x':0,'y':0,'width':160,'height':120,'fill':'#d4e6b3','radius':0,'d':'M0 65Q35 20 80 65T160 65V120H0Z','z_index':20}
 person={'id':'character','entity_id':'whole-character','name':'完整角色','kind':'person','parent':None,'box':{'left':50,'top':5,'right':110,'bottom':110},'z_index':30}
 return raw,{'project_name':'合成遮挡测试','assets':[person],'texts':[],'art_text_ids':[],'text_corrections':[],'vectors':[plane,rear],'groups':[],'warnings':[]}

class ForegroundPlanningTests(unittest.TestCase):
 def test_actual_first_scan_receives_conditional_foreground_and_occlusion_contract(self):
  raw,_=fixture();seen={}
  def analyze(prompt,images,schema,*a,**k):seen.update(prompt=prompt,schema=schema);raise Captured()
  with tempfile.TemporaryDirectory() as home,patch.object(codex_pipeline.CLIENT,'analyze',side_effect=analyze),patch.object(codex_pipeline.CLIENT,'generate',side_effect=AssertionError('no paid generation')):
   with self.assertRaises(Captured):codex_pipeline._process(raw,'测试',lambda *_:None,lambda:False,raw,Path(home))
  prompt=seen['prompt'];self.assertIn('不得根据底部位置、面积大小或颜色将独立前景判成背景',prompt)
  self.assertIn('前景云地',prompt);self.assertIn('遮罩台面',prompt);self.assertIn('并非每张图都必须新增前景',prompt)
  self.assertIn('后层装饰 < 独立前景面 < 完整角色',prompt)
  vector=seen['schema']['properties']['vectors']['items'];self.assertIn('path',vector['properties']['type']['enum']);self.assertIn('z_index',vector['required'])
 def test_background_request_explicitly_removes_native_foreground_by_geometry(self):
  raw,plan=fixture();scene=engine.build_scene(raw,'测试',plan,lambda *_:None,lambda:False);seen={}
  def generate(prompt,images,target,**kw):seen['prompt']=prompt;raise Captured()
  with tempfile.TemporaryDirectory() as home,patch.object(workflow_assets.CLIENT,'generate',side_effect=generate):
   home=Path(home);assets=home/'project/1_过程/01_素材';structure=home/'project/1_过程/02_结构';assets.mkdir(parents=True);structure.mkdir();source=home/'source.png';Image.new('RGB',(160,120),'#8877aa').save(source)
   with self.assertRaises(Captured):workflow_assets.complete_background(source,scene,assets,structure,lambda:False,force_repair=True)
  prompt=seen['prompt'];self.assertIn('原生矢量前景也必须移除',prompt);self.assertIn('不得烘焙进干净背景',prompt);self.assertIn('独立前景面',prompt);self.assertIn('sourceVectorId',prompt);self.assertIn('z_index',prompt)
 def test_actual_scene_preserves_large_flat_foreground_between_rear_and_whole_character(self):
  raw,plan=fixture();scene=engine.build_scene(raw,'测试',plan,lambda *_:None,lambda:False)
  ordered=[n.get('sourceVectorId') or n.get('sourceEntityId') for n in scene['nodes'][1:]]
  self.assertEqual(ordered,['rear','plane','whole-character'])
  plane=scene['nodes'][2];self.assertEqual(plane['type'],'path');self.assertEqual(plane['fill'],'#d4e6b3');self.assertGreater(plane['width']*plane['height'],scene['width']*scene['height']*.93)
  self.assertEqual(sum(n.get('sourceEntityId')=='whole-character' for n in scene['nodes']),1)
 def test_opposite_observed_occlusion_can_place_foreground_above_character(self):
  raw,plan=fixture();plan['vectors'][0]['z_index']=40;scene=engine.build_scene(raw,'测试',plan,lambda *_:None,lambda:False)
  self.assertEqual([n.get('sourceVectorId') or n.get('sourceEntityId') for n in scene['nodes'][1:]],['rear','whole-character','plane'])
 def test_no_foreground_evidence_does_not_invent_an_extra_plane(self):
  raw,plan=fixture();plan['vectors']=[];scene=engine.build_scene(raw,'测试',plan,lambda *_:None,lambda:False)
  self.assertEqual(len(scene['nodes']),2);self.assertFalse(any(n.get('sourceVectorId') for n in scene['nodes']))

if __name__=='__main__':unittest.main()
