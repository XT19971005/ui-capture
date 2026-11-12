import json,sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auto_expert import bind_external_plan,check_bound_plan

class ExternalPlanTests(unittest.TestCase):
 def test_runtime_rejects_stale_knowledge_and_retains_unimplemented_requirements(self):
  from knowledge_store import make_bundle
  bundle=make_bundle('test',[{'path':'a','content':'孔洞与同款'}],{})
  value=self.plan();value['knowledge_ack']=bundle['receipt'];value['pending_requirements']=['实例复用待实现']
  rgb=np.zeros((100,200,3),np.uint8)
  p=bind_external_plan(json.dumps(value),rgb,{},knowledge=bundle)
  self.assertEqual(p['knowledge_receipt'],bundle['receipt'])
  self.assertEqual(p['pending_requirements'],value['pending_requirements'])
  del value['knowledge_ack']
  with self.assertRaises(ValueError):bind_external_plan(json.dumps(value),rgb,{},knowledge=bundle)
 def test_explicit_pixel_coordinates_are_not_scaled_twice(self):
  rgb=np.zeros((100,200,3),np.uint8);value=self.plan();value.update(coordinate_space='pixels',width=200,height=100);value['assets'][0]['box']=[10,20,70,90]
  p=bind_external_plan(json.dumps(value),rgb,{})
  self.assertEqual(p['assets'][0]['box'],[10,20,70,90])
  value['height']=101
  with self.assertRaises(ValueError):bind_external_plan(json.dumps(value),rgb,{})
 def plan(self):return {'assets':[{'id':'a','name':'实际标识','kind':'neon','box':[100,100,300,500]}],'background_prompt':'empty blue gradient','warnings':[]}
 def test_external_reply_is_validated_scaled_and_bound_to_actual_image(self):
  rgb=np.zeros((100,200,3),np.uint8)
  p=bind_external_plan('```json\n'+json.dumps(self.plan())+'\n```',rgb,{'texts':[]})
  self.assertEqual(p['assets'][0]['box'],[20,10,60,50]);check_bound_plan(p,rgb)
  self.assertEqual(p['expert_source'],'platform_company_api')
 def test_truncated_or_invalid_coordinates_are_not_repaired(self):
  rgb=np.zeros((100,200,3),np.uint8)
  for text in ['{"assets":[',json.dumps(dict(self.plan(),assets=[]))]:
   with self.assertRaises(ValueError):bind_external_plan(text,rgb,{})
 def test_ocr_supplement_retains_repeated_instances(self):
  rgb=np.zeros((100,200,3),np.uint8)
  p=bind_external_plan(json.dumps(self.plan()),rgb,{'texts':[{'text':'OK','box':[100,5,130,20]},{'text':'OK','box':[160,5,190,20]}]})
  self.assertEqual(sum(a.get('text')=='OK' for a in p['assets']),2)
