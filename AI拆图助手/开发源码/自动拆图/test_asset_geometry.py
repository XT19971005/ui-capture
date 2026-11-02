import base64,io,unittest
from PIL import Image

class GeometryTests(unittest.TestCase):
 def test_repeated_pixel_repair_uses_world_alpha_bounds_not_padded_canvas(self):
  from asset_geometry import extraction_bounds
  im=Image.new('RGBA',(200,200));im.paste('red',(50,75,150,125));f=io.BytesIO();im.save(f,'PNG')
  node={'x':-40,'y':-55,'width':200,'height':200,'src':'data:image/png;base64,'+base64.b64encode(f.getvalue()).decode()}
  self.assertEqual(extraction_bounds(node),[10,20,100,50])
  node['_placementBounds']={'x':-20,'y':600,'width':100,'height':150}
  self.assertEqual(extraction_bounds(node),[-20,600,100,150])
 def test_reposition_uses_visible_alpha_and_keeps_original_bytes(self):
  from asset_geometry import correct_placement
  im=Image.new('RGBA',(200,200));im.paste('red',(50,75,150,125));f=io.BytesIO();im.save(f,'PNG')
  node={'id':'fan','type':'image','x':0,'y':0,'width':40,'height':40,'src':'data:image/png;base64,'+base64.b64encode(f.getvalue()).decode()}
  p={'x':10,'y':20,'width':100,'height':50,'confidence':.97,'evidence':'原图扇子轮廓与展开边界清楚可见','contentCorrect':True}
  result=correct_placement(node,p,{'width':800,'height':800})
  self.assertEqual((result['x'],result['y'],result['width'],result['height']),(-40,-55,200,200))
  self.assertEqual(result['src'],node['src']);self.assertEqual(node['width'],40)
 def test_uncertain_or_nonfinite_geometry_is_rejected(self):
  from asset_geometry import validate_placement
  p={'x':0,'y':0,'width':100,'height':50,'confidence':.5,'evidence':'尺寸不确定，不能据此自动改动','contentCorrect':True}
  with self.assertRaises(ValueError):validate_placement(p,{'width':800,'height':800})
  p.update(confidence=.99,width=float('nan'))
  with self.assertRaises(ValueError):validate_placement(p,{'width':800,'height':800})
 def test_edge_object_may_extend_outside_canvas_but_must_intersect(self):
  from asset_geometry import validate_placement
  p={'x':-60,'y':600,'width':150,'height':180,'confidence':.97,'evidence':'左侧扇子在画布边缘裁断，完整轮廓延伸至画布外','contentCorrect':True}
  self.assertEqual(validate_placement(p,{'width':800,'height':800})['x'],-60)
  p['x']=-200
  with self.assertRaises(ValueError):validate_placement(p,{'width':800,'height':800})
