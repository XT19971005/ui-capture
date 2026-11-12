import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auto_expert import validate_advice,complete_ocr,bind_plan,check_bound_plan

class AutoExpertTests(unittest.TestCase):
 def test_model_inventory_accepts_complete_fenced_array_but_rejects_repetition(self):
  from auto_expert import parse_inventory
  self.assertEqual(parse_inventory('```json\n[{"name":"人物","kind":"person"}]\n```'),[{'name':'人物','kind':'person'}])
  with self.assertRaisesRegex(ValueError,'重复'):parse_inventory('[{"name":"欢","kind":"neon"},{"name":"欢","kind":"neon"}]')
  with self.assertRaises(ValueError):parse_inventory('[{"name":"欢","kind":"neon"},')
 def test_valid_inventory_and_matching_regions_are_bound_to_source(self):
  from auto_expert import analyze_auto
  import json
  image=np.zeros((486,1000,3),np.uint8)
  responses=iter([json.dumps({'inventory':[{'name':'人物','kind':'person'}]}),json.dumps(self.plan())])
  p=analyze_auto(image,'unused','unused',{},runner=lambda *a,**k:next(responses))
  check_bound_plan(p,image)
  self.assertEqual(p['inventory'],[{'name':'人物','kind':'person'}])
 def test_inventory_failure_keeps_bounded_model_evidence(self):
  from auto_expert import analyze_auto
  with self.assertRaisesRegex(ValueError,'RAW_MARKER'):
   analyze_auto(np.zeros((10,10,3),np.uint8),'unused','unused',{},runner=lambda *a,**k:'RAW_MARKER invalid model response')
 def test_repeated_text_at_different_positions_is_not_dropped(self):
  p=validate_advice(self.plan(),1000,486)
  complete_ocr(p,{'texts':[{'text':'OK','box':b} for b in [[10,10,40,30],[900,10,940,30]]]})
  self.assertEqual(sum(a.get('text')=='OK' for a in p['assets']),2)
 def test_inventory_is_checked_before_coordinate_execution(self):
  from auto_expert import analyze_auto
  import json
  responses=iter([json.dumps({'inventory':[{'name':'人物','kind':'person'},{'name':'标识','kind':'flat_shape'}]}),json.dumps(self.plan()),json.dumps(self.plan())])
  with self.assertRaisesRegex(ValueError,'标识'):
   analyze_auto(np.zeros((486,1000,3),np.uint8),'unused','unused',{'texts':[]},runner=lambda *a,**kw:next(responses))
 def plan(self):return {'assets':[{'id':'hero','name':'人物','kind':'person','box':[100,0,800,1000],'occluded':False}],'background_prompt':'Empty blue studio gradient','warnings':[]}
 def test_regions_come_from_model_and_scale_to_actual_canvas(self):
  p=validate_advice(self.plan(),1000,486)
  self.assertEqual(p['assets'][0]['box'],[100,0,800,486])
  self.assertEqual(len(p['assets']),1)
 def test_bad_regions_duplicate_ids_or_missing_assets_do_not_fall_back(self):
  for change in [{'assets':[]},{'assets':[{'id':'a','name':'x','kind':'image','box':[0,0,1001,1000]}]},{'assets':self.plan()['assets']*2}]:
   p=self.plan();p.update(change)
   with self.assertRaises(ValueError):validate_advice(p,1000,486)
 def test_ocr_rows_are_not_silently_discarded_or_spaces_removed(self):
  p=validate_advice(self.plan(),1000,486)
  complete_ocr(p,{'texts':[{'text':'of the Dragon','box':[820,10,980,30],'color':[255,255,255]}]})
  self.assertEqual(p['assets'][-1]['text'],'of the Dragon')
 def test_plan_cannot_be_applied_to_another_image(self):
  a=np.zeros((10,20,3),dtype=np.uint8);p=bind_plan(validate_advice(self.plan(),20,10),a)
  check_bound_plan(p,a)
  b=a.copy();b[0,0]=1
  with self.assertRaises(ValueError):check_bound_plan(p,b)
