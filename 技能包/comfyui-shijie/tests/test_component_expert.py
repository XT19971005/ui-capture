import sys,json,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from component_expert import build_request,bind_plan
from knowledge_store import load_knowledge

class ExpertContractTests(unittest.TestCase):
 def setUp(self):
  self.rgb=np.zeros((60,100,3),np.uint8);self.k=load_knowledge()
  self.plan=dict(width=100,height=60,knowledge_ack=self.k['receipt'],background_prompt='Clean scenic background without UI',assets=[dict(id='a',name='底板',box=[2,2,98,58],method='source',z=1,group='控件')])
 def test_full_sources_and_actual_size(self):
  prompt=build_request(self.rgb,self.k)
  for row in self.k['sources']:self.assertIn(row['content'],prompt)
  self.assertIn('100',prompt);self.assertIn('components-v1',prompt)
 def test_attachment_mode_keeps_dynamic_task_and_receipt(self):
  prompt=build_request(self.rgb,self.k,knowledge_attachment=True)
  self.assertLess(len(prompt),5000);self.assertIn(self.k['sha256'],prompt)
  self.assertIn('width=100,height=60',prompt);self.assertIn('13',prompt)
 def test_bound_to_current_pixels(self):
  a=bind_plan(json.dumps(self.plan),self.rgb,self.k)
  self.assertEqual(a['pipeline'],'components-v1');self.assertEqual(len(a['source_sha256']),64)
 def test_rejects_old_receipt_and_bad_geometry(self):
  for field,value in [('knowledge_ack',{}),('width',99)]:
   p=dict(self.plan);p[field]=value
   with self.assertRaises(ValueError):bind_plan(json.dumps(p),self.rgb,self.k)
  self.plan['assets'][0]['box']=[0,0,101,60]
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)
 def test_rejects_duplicate_order_and_unknown_method(self):
  self.plan['assets'].append(dict(self.plan['assets'][0],id='b'))
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)
  self.plan['assets']=self.plan['assets'][:1];self.plan['assets'][0]['method']='run_code'
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)
 def test_rejects_outside_clear_and_nonfinite(self):
  row=self.plan['assets'][0];row['clear_boxes']=[[0,0,10,10]]
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)
  row.pop('clear_boxes');row['radius']=float('nan')
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)
 def test_small_bbox_rounding_expands_crop_without_changing_path(self):
  row=self.plan['assets'][0];row['polygon']=[[2,1],[98,2],[98,58],[2,58]]
  bound=bind_plan(json.dumps(self.plan),self.rgb,self.k)
  self.assertEqual(bound['assets'][0]['box'],[2,1,98,58])
  self.assertEqual(bound['assets'][0]['polygon'],row['polygon'])
  self.assertTrue(bound['coordinate_adjustments'])
  row['polygon'][0]=[2,-1]
  with self.assertRaises(ValueError):bind_plan(json.dumps(self.plan),self.rgb,self.k)

if __name__=='__main__':unittest.main()
