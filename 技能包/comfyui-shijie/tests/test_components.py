import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from components import component_mask,clean_surface,repair_background
class ComponentTests(unittest.TestCase):
 def test_polygon_and_hole(self):
  m=component_mask(80,60,dict(box=[10,10,70,50],polygon=[[10,10],[70,10],[70,50],[10,50]],holes=[[[30,20],[50,20],[50,40],[30,40]]]))
  self.assertEqual(m[30,40],0);self.assertEqual(m[15,15],255);self.assertEqual(m[0,0],0)
 def test_clean_only_explicit_exclusion(self):
  a=np.full((60,80,3),130,np.uint8);a[20:30,20:30]=240
  b=clean_surface(a,[[18,18,32,32]])
  self.assertTrue(np.array_equal(a[:15],b[:15]));self.assertLess(int(b[25,25,0]),150)
 def test_background_patch_is_bounded(self):
  a=np.full((60,80,3),90,np.uint8);a[30:35,55:60]=255
  b=repair_background(a,[[50,25,65,40]])
  m=np.ones((60,80),bool);m[25:40,50:65]=False
  self.assertTrue(np.array_equal(a[m],b[m]));self.assertLess(int(b[32,57,0]),120)
class ComponentExecutionTests(unittest.TestCase):
 def test_latin_multiline_does_not_require_raqm(self):
  from unittest.mock import patch
  from PIL import ImageFont
  from exporter import _text_image
  original=ImageFont.truetype
  def require_basic(*args,**kwargs):
   if kwargs.get('layout_engine')!=ImageFont.Layout.BASIC:raise RuntimeError('raqm_layout() failed.')
   return original(*args,**kwargs)
  with patch('exporter.ImageFont.truetype',side_effect=require_basic):
   rgba,native=_text_image(dict(box=[0,0,100,80],text='Corn\nCardigan',color=[30,30,30]),Path('C:/Windows/Fonts/arial.ttf'),100,80)
  self.assertEqual(native['text'],'Corn\nCardigan');self.assertGreater(np.count_nonzero(rgba[:,:,3]),100)
 def test_estimated_color_recovers_thin_mark_without_paper(self):
  from unittest.mock import patch
  import types
  from components import execute_components
  rgb=np.full((30,70,3),235,np.uint8);rgb[12:16,8:62]=[156,148,182]
  row=dict(id='mark',name='mark',box=[0,0,70,30],method='shape',color=[129,126,191],tolerance=45,z=0)
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace()}):
   _,assets,warnings=execute_components(rgb,{'assets':[row]}, {},[],None,None)
  self.assertEqual(len(assets),1);self.assertEqual(assets[0]['kind'],'shape')
  self.assertTrue(any('calibrated' in w for w in warnings))
  self.assertLess(assets[0]['rgba'].shape[0],10)
 def test_native_text_and_group_survive_tight_storage(self):
  from unittest.mock import patch
  import types
  from components import execute_components
  rgb=np.full((60,160,3),180,np.uint8)
  row=dict(id='title',name='Title',box=[20,10,140,50],method='text',text='Care',color=[60,30,10],z=0,group='标题')
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace()}):
   _,assets,_=execute_components(rgb,{'assets':[row]}, {},[Path('C:/Windows/Fonts/arial.ttf')],None,None)
  self.assertEqual(assets[0]['kind'],'text');self.assertEqual(assets[0]['group'],'标题')
  self.assertGreaterEqual(assets[0]['left'],20);self.assertEqual(assets[0]['text']['text'],'Care')
 def test_shape_hole_is_native_and_background_not_selected(self):
  from unittest.mock import patch
  import types
  from components import execute_components
  rgb=np.full((40,40,3),240,np.uint8);rgb[5:35,5:35]=30;rgb[15:25,15:25]=240
  row=dict(id='s',name='环',box=[0,0,40,40],method='shape',color=[30,30,30],z=0)
  with patch.dict(sys.modules,{'torch':types.SimpleNamespace()}):
   _,assets,_=execute_components(rgb,{'assets':[row]}, {},[],None,None)
  self.assertEqual(assets[0]['kind'],'shape');self.assertEqual(assets[0]['rgba'][15,15,3],0)
if __name__=="__main__":unittest.main()
