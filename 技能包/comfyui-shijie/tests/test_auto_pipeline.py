import json,sys,tempfile,unittest,types
from unittest.mock import patch
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from auto_pipeline import invoke,flat_asset,execute_plan
from auto_expert import bind_plan
from exporter import export_scene

class PipelineTests(unittest.TestCase):
 def test_empty_neon_is_rejected_but_low_alpha_is_not_called_empty(self):
  from auto_pipeline import require_visible_asset
  rgba=np.zeros((8,8,4),np.uint8)
  with self.assertRaisesRegex(ValueError,'空素材'):require_visible_asset(rgba,'霓虹')
  rgba[2:5,2:5,3]=1
  require_visible_asset(rgba,'淡阴影')
 def test_native_text_uses_layer_order_for_person_occlusion(self):
  class Tensor:
   def __init__(self,v):self.v=v
   def unsqueeze(self,*a):return self
   def detach(self):return self
   def cpu(self):return self
   def numpy(self):return self.v
  class Remove:
   FUNCTION='run'
   def run(self,**kw):return (Tensor(np.ones((1,10,10))),)
  rgb=np.full((10,10,3),100,np.uint8)
  plan=bind_plan({'format':'qp-auto-plan-v1','width':10,'height':10,'assets':[{'id':'p','name':'人物','kind':'person','box':[0,0,10,10]},{'id':'t','name':'标题','kind':'text','box':[0,0,10,10],'text':'A'}],'background_prompt':'blue'},rgb)
  native={'kind':'text','name':'标题','rgba':np.full((10,10,4),255,np.uint8),'text':{'text':'A'}}
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace(from_numpy=Tensor)}),patch('auto_pipeline.prepare_text',return_value=(None,{'assets':[native],'warnings':[]})):
   _,assets,_=execute_plan(rgb,plan,{'RemoveBackground':Remove},[],'传统修补候选',removal_model=object())
  self.assertEqual([a['name'] for a in assets],['标题','人物'])
  self.assertTrue(np.all(assets[0]['rgba'][...,3]==255))
 def test_preloaded_model_does_not_require_loader_directory_discovery(self):
  class Tensor:
   def __init__(self,value):self.value=value
   def unsqueeze(self,*args):return self
   def detach(self):return self
   def cpu(self):return self
   def numpy(self):return self.value
  supplied=object()
  class Remove:
   FUNCTION='run'
   def run(self,bg_removal_model,image):
    if bg_removal_model is not supplied:raise AssertionError('wrong model')
    return (Tensor(np.ones((1,10,10))),)
  rgb=np.full((10,10,3),100,np.uint8)
  plan=bind_plan({'format':'qp-auto-plan-v1','width':10,'height':10,'assets':[{'id':'p','name':'person','kind':'person','box':[0,0,10,10]}],'background_prompt':'blue','warnings':[]},rgb)
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace(from_numpy=Tensor)}):
   _,assets,_=execute_plan(rgb,plan,{'RemoveBackground':Remove},[],'传统修补候选',removal_model=supplied)
  self.assertEqual(len(assets),1)

 def test_registry_call_uses_named_parameters_and_rejects_empty_result(self):
  class Fake:
   FUNCTION='run'
   def run(self,x):return {'result':(x+1,)}
  self.assertEqual(invoke({'Fake':Fake},'Fake',x=3),(4,))
  with self.assertRaises(RuntimeError):invoke({},'Missing')
 def test_white_ring_has_native_hole_and_exports_real_shape(self):
  rgb=np.zeros((80,100,3),np.uint8);rgb[:]=[20,55,90];rgb[15:65,20:80]=255;rgb[30:50,35:65]=[20,55,90]
  a=flat_asset(rgb,{'name':'白色标识','box':[10,5,90,75],'color':[255,255,255]},None)
  self.assertEqual(a['kind'],'shape');self.assertTrue(any(p['operation']=='subtract' for p in a['shapes']))
  with tempfile.TemporaryDirectory() as temp:
   report=export_scene([np.dstack([rgb,np.full(rgb.shape[:2],255,np.uint8)])],{'texts':[]},temp,'vector-test',None,False,False,prepared_assets=[a])
   sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'依赖/Python'))
   from psd_tools import PSDImage
   psd=PSDImage.open(report['psd']);self.assertEqual(sum(l.kind=='shape' for l in psd.descendants()),1)
 def test_gradient_is_not_misreported_as_flat_vector(self):
  rgb=np.zeros((80,100,3),np.uint8);rgb[:]=[10,20,30]
  rgb[10:70,10:90]=np.linspace(170,255,80).astype(np.uint8)[None,:,None]
  a=flat_asset(rgb,{'name':'渐变','box':[5,5,95,75],'color':[225,225,225]},None)
  self.assertEqual(a['kind'],'bitmap')
