"""Offline replacement boundaries; the only fake is the paid image generator."""
import base64,copy,hashlib,io,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

def pixels(src):
 return Image.open(io.BytesIO(base64.b64decode(src.split(',',1)[1]))).convert('RGBA')

def generation_scene(size=(1024,1024),transparent=False):
 src=png(Image.new('RGBA',size,(0,0,0,0) if transparent else (255,255,255,255)))
 width,height=size
 return {'format':'shijie-scene','version':2,'title':'new image','width':width,'height':height,'source':src,'originalSource':src,'comparisonSource':src,'originalSize':{'width':width,'height':height},'provenance':'user-image','nodes':[{'id':'generated-image','type':'image','name':'new image','src':src,'x':0,'y':0,'width':width,'height':height,'locked':True,'provenance':'imported-source'}],'groups':[],'edges':[]}

class ImageReplaceTests(unittest.TestCase):
 def setUp(self):
  im=Image.new('RGBA',(8,6));im.putdata([(x*20,y*30,17,(x+y)*17) for y in range(6) for x in range(8)])
  self.source=png(im)
  self.scene={'format':'shijie-scene','version':2,'width':8,'height':6,'title':'fixture','source':self.source,'originalSource':self.source,'recognition':{'status':'PASS','reviewStatus':'PASS'},'nodes':[{'id':'a','name':'target','type':'image','src':self.source,'x':20,'y':30,'width':80,'height':60,'rotation':30,'mask':{'src':self.source},'sourceAssetId':'asset','sourceBox':{'x0':0,'y0':0,'x1':8,'y1':6},'generationRecord':{'actualImageGeneration':True},'assetReviewStatus':'PASS'},{'id':'b','name':'other','type':'rect','x':1,'y':1,'width':2,'height':2}],'groups':[{'id':'g','children':['a']}],'edges':[],'_initialSplitBaseline':{'version':1,'secret':'BASELINE_NOT_MODEL_INPUT'}}
  self.request={'targetId':'a','region':{'x':2,'y':1,'width':3,'height':2},'prompt':'replace with blue vase','reference':None}
  self.calls=[]
 def generate(self,prompt,images,target,**kwargs):
  self.calls.append((prompt,[pixels(png(Image.open(p))) for p in images],kwargs))
  with Image.open(images[0]) as canvas:size=(canvas.width*2,canvas.height*2)
  Image.new('RGBA',size,(10,20,230,117)).save(target)
  return {'file':str(target),'size':list(size),'actualImageGeneration':True,'transparent':kwargs.get('transparent',False)}
 def run_replace(self,request=None,scene=None,cancelled=lambda:False,generator=None):
  import image_replace
  with tempfile.TemporaryDirectory() as folder,patch('codex_client.CLIENT.generate',side_effect=generator or self.generate):
   return image_replace._process(self.source,'fixture',lambda *_:None,cancelled,self.source,Path(folder),scene or self.scene,request or self.request)
 def test_local_replacement_keeps_outside_rgba_geometry_other_layers_and_baseline(self):
  before=copy.deepcopy(self.scene);result=self.run_replace();im=pixels(result['nodes'][0]['src']);old=pixels(self.source)
  self.assertEqual(im.size,(8,6))
  for y in range(6):
   for x in range(8):
    if 2<=x<5 and 1<=y<3:
     self.assertEqual(im.getpixel((x,y))[3],117)
     for actual,expected in zip(im.getpixel((x,y))[:3],(10,20,230)):self.assertLessEqual(abs(actual-expected),2)
    else:self.assertEqual(im.getpixel((x,y)),old.getpixel((x,y)))
  for key in ('x','y','width','height','rotation','mask','sourceAssetId','sourceBox'):self.assertEqual(result['nodes'][0][key],before['nodes'][0][key])
  for key in ('source','originalSource','groups','edges','_initialSplitBaseline'):self.assertEqual(result[key],before[key])
  self.assertEqual(result['nodes'][1],before['nodes'][1]);self.assertEqual(self.scene,before)
  self.assertNotIn('BASELINE_NOT_MODEL_INPUT',self.calls[0][0]);self.assertTrue(self.calls[0][2]['allow_identity_change'])
  self.assertEqual(result['nodes'][0]['generationRecord']['generatedAssetSHA256'],hashlib.sha256(base64.b64decode(result['nodes'][0]['src'].split(',')[1])).hexdigest())
  self.assertEqual(result['nodes'][0]['assetReviewStatus'],'NOT_REVIEWED');self.assertNotEqual(result['recognition']['reviewStatus'],'PASS')
 def test_whole_layer_reference_is_cropped_in_its_own_natural_coordinates(self):
  ref=Image.new('RGBA',(20,12),'red');ref.paste((0,255,0,255),(10,5,14,8))
  result=self.run_replace({**self.request,'region':None,'prompt':'','reference':{'src':png(ref),'region':{'x':10,'y':5,'width':4,'height':3}}})
  self.assertEqual(self.calls[0][1][1].size,(4,3));self.assertEqual(self.calls[0][1][1].getpixel((0,0)),(0,255,0,255))
  self.assertEqual(pixels(result['nodes'][0]['src']).getpixel((0,0))[3],117)
 def test_concave_polygon_changes_only_selected_rgba_and_records_selection(self):
  selection={'type':'polygon','points':[[1,1],[7,1],[7,3],[3,3],[3,5],[1,5]]}
  request={**self.request,'region':{'x':1,'y':1,'width':6,'height':4},'selection':selection}
  before=copy.deepcopy(self.scene)
  def generate(prompt,images,target,**kwargs):
   self.calls.append((prompt,[pixels(png(Image.open(p))) for p in images],kwargs))
   Image.new('RGBA',(8,8),(231,41,9,0)).save(target)
   return {'actualImageGeneration':True}
  result=self.run_replace(request,generator=generate);actual=pixels(result['nodes'][0]['src']);old=pixels(self.source)
  for y in range(6):
   for x in range(8):
    inside=(1<=y<3 and 1<=x<7) or (3<=y<5 and 1<=x<3)
    self.assertEqual(actual.getpixel((x,y)),(231,41,9,0) if inside else old.getpixel((x,y)),(x,y))
  self.assertEqual(result['nodes'][0]['imageReplacement']['selection'],selection)
  self.assertEqual(result['recognition']['imageReplacement']['selection'],selection)
  self.assertEqual(self.scene,before)
  self.assertEqual(result['_initialSplitBaseline'],before['_initialSplitBaseline'])
  self.assertIn('奇偶',self.calls[0][0]);self.assertEqual(len(self.calls[0][1]),2)
  mask=self.calls[0][1][-1]
  self.assertEqual(mask.size,(8,8));self.assertEqual(mask.getpixel((2,5)),(255,255,255,255));self.assertEqual(mask.getpixel((5,5)),(0,0,0,255))
 def test_polygon_context_mask_and_reference_use_correct_attachment_coordinates(self):
  source=Image.new('RGBA',(100,80),(17,19,23,0));scene=copy.deepcopy(self.scene);scene['nodes'][0]['src']=png(source)
  selection={'type':'polygon','points':[[30,20],[70,20],[70,30],[40,30],[40,50],[30,50]]}
  request={**self.request,'region':{'x':30,'y':20,'width':40,'height':30},'selection':selection,'reference':{'src':png(Image.new('RGBA',(2,3),'red'))}}
  def generate(prompt,images,target,**kwargs):
   self.assertEqual(len(images),3)
   with Image.open(images[0]) as context:self.assertEqual(context.size,(64,64));self.assertEqual(context.getpixel((0,8)),source.getpixel((18,11)))
   with Image.open(images[1]) as ref:self.assertEqual(ref.size,(2,3))
   with Image.open(images[2]) as mask:
    self.assertEqual(mask.size,(64,64));self.assertEqual(mask.convert('L').getpixel((12,17)),255)
    self.assertEqual(mask.convert('L').getpixel((32,37)),0);self.assertEqual(mask.convert('L').getpixel((0,0)),0)
   self.assertIn('[12, 17]',prompt)
   Image.new('RGBA',(128,128),(10,20,230,117)).save(target);return {'actualImageGeneration':True}
  result=self.run_replace(request,scene=scene,generator=generate);actual=pixels(result['nodes'][0]['src'])
  self.assertEqual(actual.size,(100,80));self.assertEqual(actual.getpixel((35,40))[3],117)
  self.assertEqual(actual.getpixel((50,40)),source.getpixel((50,40)));self.assertEqual(actual.getpixel((29,20)),source.getpixel((29,20)))
 def test_self_intersecting_zero_signed_area_polygon_uses_evenodd_fill(self):
  request={**self.request,'region':{'x':1,'y':1,'width':6,'height':4},'selection':{'type':'polygon','points':[[1,1],[7,5],[1,5],[7,1]]}}
  result=self.run_replace(request);actual=pixels(result['nodes'][0]['src']);old=pixels(self.source)
  for point in ((3,1),(4,1),(3,4),(4,4)):self.assertEqual(actual.getpixel(point)[3],117)
  for point in ((1,2),(6,2),(1,3),(6,3)):self.assertEqual(actual.getpixel(point),old.getpixel(point))
 def test_polygon_maximum_budget_and_inclusive_image_edge_are_valid(self):
  import image_replace
  points=[[0,0],[8,0],[8,6],[0,6]]+[[0,6]]*2044
  request={**self.request,'region':{'x':0,'y':0,'width':8,'height':6},'selection':{'type':'polygon','points':points}}
  spec=image_replace.validate_replacement(self.scene,request)
  self.assertEqual(spec['selection'],request['selection'])
  result=self.run_replace(request);actual=pixels(result['nodes'][0]['src'])
  self.assertEqual(actual.getpixel((0,0))[3],117);self.assertEqual(actual.getpixel((7,5))[3],117)
 def test_invalid_polygons_are_rejected_before_generation(self):
  good={'type':'polygon','points':[[2,1],[5,1],[5,3],[2,3]]}
  bad=[False,[],{}, {'type':'rect','points':good['points']},{**good,'extra':1},
       {'type':'polygon','points':[[2,1],[5,1]]},
       {'type':'polygon','points':good['points']+[[2,3]]*2045},
       {'type':'polygon','points':[[2,1],[5,1],[5,1]]},
       {'type':'polygon','points':[[2,1],[3,2],[4,3]]},
       {'type':'polygon','points':good['points']*2}]
  for value in (True,2.5,float('nan'),float('inf'),-1,9,'2',None):bad.append({'type':'polygon','points':[[value,1],[5,1],[5,3],[2,3]]})
  for point in ([2], [2,1,0], {'x':2,'y':1}):bad.append({'type':'polygon','points':[point,[5,1],[5,3],[2,3]]})
  for selection in bad:
   with self.subTest(selection=selection),self.assertRaises(ValueError):self.run_replace({**self.request,'selection':selection})
  for region in (None,{'x':1,'y':1,'width':4,'height':2}):
   with self.subTest(region=region),self.assertRaises(ValueError):self.run_replace({**self.request,'selection':good,'region':region})
  # This nonzero-area triangle has no interior pixel centers under the binary fill rule.
  with self.assertRaises(ValueError):self.run_replace({**self.request,'region':{'x':0,'y':0,'width':1,'height':1},'selection':{'type':'polygon','points':[[0,0],[0,1],[1,1]]}})
  self.assertFalse(self.calls)
 def test_explicit_null_selection_preserves_rectangle_and_whole_layer_behavior(self):
  for region in (self.request['region'],None):
   request={**self.request,'region':region}
   old=self.run_replace(request);new=self.run_replace({**request,'selection':None})
   self.assertEqual(pixels(old['nodes'][0]['src']).tobytes(),pixels(new['nodes'][0]['src']).tobytes())
 def test_multiple_disjoint_and_overlapping_polygons_form_union_not_xor(self):
  first=[[1,1],[4,1],[4,4],[1,4]]
  cases=[([[5,2],[7,2],[7,5],[5,5]],lambda x,y:5<=x<7 and 2<=y<5),
         ([[3,2],[7,2],[7,5],[3,5]],lambda x,y:3<=x<7 and 2<=y<5)]
  for second,second_inside in cases:
   selection={'type':'polygons','polygons':[first,second]}
   request={**self.request,'region':{'x':1,'y':1,'width':6,'height':4},'selection':selection}
   def generate(prompt,images,target,**kwargs):
    self.assertIn('并集',prompt)
    with Image.open(images[-1]) as mask:
     for y in range(6):
      for x in range(8):self.assertEqual(mask.getpixel((x,y+1)),255 if (1<=x<4 and 1<=y<4) or second_inside(x,y) else 0)
    Image.new('RGBA',(8,8),(211,17,93,0)).save(target);return {'actualImageGeneration':True}
   with self.subTest(second=second):
    result=self.run_replace(request,generator=generate);actual=pixels(result['nodes'][0]['src']);old=pixels(self.source)
    for y in range(6):
     for x in range(8):self.assertEqual(actual.getpixel((x,y)),(211,17,93,0) if (1<=x<4 and 1<=y<4) or second_inside(x,y) else old.getpixel((x,y)),(x,y))
    self.assertEqual(result['nodes'][0]['imageReplacement']['selection'],selection)
    self.assertEqual(result['recognition']['imageReplacement']['selection'],selection)
 def test_multiple_polygon_aggregate_budget_and_count_boundaries(self):
  import image_replace
  square=[[2,1],[5,1],[5,3],[2,3]]
  polygons=[square+[[2,3]]*60 for _ in range(32)]
  request={**self.request,'selection':{'type':'polygons','polygons':polygons}}
  spec=image_replace.validate_replacement(self.scene,request)
  self.assertEqual(spec['selection'],request['selection']);self.assertEqual(spec['selectionMask'].tobytes(),bytes([255])*6)
  for bad in ([],[square]*33,[square+[[2,3]]*1021,square+[[2,3]]*1020],[square,[]],[square,[[2,1],[3,2],[4,3]]],[square,False],False):
   with self.subTest(count=len(bad) if isinstance(bad,list) else None),self.assertRaises(ValueError):self.run_replace({**self.request,'selection':{'type':'polygons','polygons':bad}})
  for selection in ({'type':'polygons','polygons':[square],'points':square},{'type':'polygons','points':square},{'type':'polygons','polygons':[[[True,1],[5,1],[5,3]]]}):
   with self.subTest(selection=selection),self.assertRaises(ValueError):self.run_replace({**self.request,'selection':selection})
  with self.assertRaises(ValueError):self.run_replace({**request,'region':{'x':1,'y':1,'width':4,'height':2}})
  self.assertFalse(self.calls)
 def test_multiselection_keeps_evenodd_rule_within_each_polygon(self):
  figure_eight=[[1,1],[7,5],[1,5],[7,1]]
  request={**self.request,'region':{'x':1,'y':1,'width':6,'height':4},'selection':{'type':'polygons','polygons':[figure_eight,figure_eight]}}
  result=self.run_replace(request);actual=pixels(result['nodes'][0]['src']);old=pixels(self.source)
  for point in ((3,1),(4,1),(3,4),(4,4)):self.assertEqual(actual.getpixel(point)[3],117)
  for point in ((1,2),(6,2),(1,3),(6,3)):self.assertEqual(actual.getpixel(point),old.getpixel(point))
 def test_different_generated_aspect_is_rejected_instead_of_stretching(self):
  before=copy.deepcopy(self.scene)
  for size in ((16,13),(12,16),(16,12),(1600,1202)):
   def generate(prompt,images,target,**kwargs):
    Image.new('RGBA',size,'blue').save(target);return {'actualImageGeneration':True}
   with self.subTest(size=size),self.assertRaisesRegex(ValueError,'比例|重试'):self.run_replace(generator=generate)
  self.assertEqual(self.scene,before)
 def test_standard_square_output_handles_actual_wide_title_and_tall_selection(self):
  # The reported title is 452x129 in 1792x828. Context is 724x207, centered
  # at (0,258) on a 724-square model canvas; tall case transposes that layout.
  cases=[((1792,828),{'x':600,'y':300,'width':452,'height':129},(724,207),(0,258),(136,297),255),
         ((828,1792),{'x':300,'y':600,'width':129,'height':452},(207,724),(258,0),(297,136),0)]
  for size,region,context_size,padding,offset,alpha in cases:
   source=Image.new('RGBA',size,(193,31,77,alpha));scene=copy.deepcopy(self.scene);scene['nodes'][0]['src']=png(source)
   def generate(prompt,images,target,**kwargs):
    with Image.open(images[0]) as canvas:
     self.assertEqual(canvas.size,(724,724));self.assertEqual(canvas.getpixel(padding),source.getpixel((0,0)))
     self.assertEqual(canvas.getpixel((0,0))[3],alpha);self.assertEqual(kwargs['transparent'],alpha<255)
    self.assertIn('1024×1024',prompt);self.assertIn('补边',prompt)
    self.assertIn('"x": '+str(offset[0]),prompt);self.assertIn('"y": '+str(offset[1]),prompt)
    generated=Image.new('RGBA',(724,724));generated.putdata([(x//4,y//4,220,255) for y in range(724) for x in range(724)])
    generated.resize((1024,1024),Image.Resampling.NEAREST).save(target);return {'actualImageGeneration':True}
   with self.subTest(size=size):
    result=self.run_replace({**self.request,'region':region},scene=scene,generator=generate);actual=pixels(result['nodes'][0]['src'])
    self.assertEqual(actual.size,size)
    for dx,dy in ((10,10),(region['width']//2,region['height']//2),(region['width']-10,region['height']-10)):
     pixel=actual.getpixel((region['x']+dx,region['y']+dy))
     self.assertLessEqual(abs(pixel[0]-(offset[0]+dx)//4),1);self.assertLessEqual(abs(pixel[1]-(offset[1]+dy)//4),1)
    actual.paste(source.crop((region['x'],region['y'],region['x']+region['width'],region['y']+region['height'])),(region['x'],region['y']))
    self.assertEqual(actual.tobytes(),source.tobytes())
 def test_whole_layer_canonical_ratios_and_arbitrary_letterbox_preserve_geometry(self):
  cases=[((90,60),(90,60),(0,0),(1536,1024)),((60,90),(60,90),(0,0),(1024,1536)),
         ((80,80),(80,80),(0,0),(1024,1024)),((90,30),(90,90),(0,30),(1024,1024)),((30,90),(90,90),(30,0),(1024,1024))]
  for size,canvas_size,padding,output_size in cases:
   source=Image.new('RGBA',size,(22,55,88,255));scene=copy.deepcopy(self.scene);scene['nodes'][0]['src']=png(source)
   def generate(prompt,images,target,**kwargs):
    with Image.open(images[0]) as canvas:self.assertEqual(canvas.size,canvas_size)
    self.assertIn(str(output_size[0])+'×'+str(output_size[1]),prompt)
    generated=Image.new('RGBA',canvas_size);generated.putdata([(x,y,17,255) for y in range(canvas_size[1]) for x in range(canvas_size[0])])
    generated.resize(output_size,Image.Resampling.NEAREST).save(target);return {'actualImageGeneration':True}
   with self.subTest(size=size):
    result=self.run_replace({**self.request,'region':None},scene=scene,generator=generate);actual=pixels(result['nodes'][0]['src'])
    self.assertEqual(actual.size,size)
    for x,y in ((0,0),(size[0]//2,size[1]//2),(size[0]-1,size[1]-1)):
     color=actual.getpixel((x,y));self.assertLessEqual(abs(color[0]-x-padding[0]),1);self.assertLessEqual(abs(color[1]-y-padding[1]),1)
 def test_unexpected_model_ratio_reports_actual_and_requested_dimensions(self):
  def generate(prompt,images,target,**kwargs):
   Image.new('RGBA',(1024,1536),'blue').save(target);return {'actualImageGeneration':True}
  with self.assertRaisesRegex(ValueError,'1024×1536.*1024×1024.*8×8'):self.run_replace(generator=generate)
 def test_matching_aspect_and_tiny_integer_rounding_keep_original_dimensions(self):
  for size in ((8,8),(16,16),(1601,1600)):
   def generate(prompt,images,target,**kwargs):
    Image.new('RGBA',size,'blue').save(target);return {'actualImageGeneration':True}
   with self.subTest(size=size):
    result=self.run_replace(generator=generate);actual=pixels(result['nodes'][0]['src'])
    self.assertEqual(actual.size,(8,6));self.assertEqual(actual.getpixel((2,1)),(0,0,255,255))
    self.assertEqual(actual.getpixel((0,0)),pixels(self.source).getpixel((0,0)))
 def test_local_generation_uses_bounded_context_and_maps_pixels_back_exactly(self):
  # Hand-derived 30% context (minimum 8px), then centered square letterbox.
  cases=[({'x':30,'y':20,'width':40,'height':30},(64,64),(18,11),(0,8),(12,17)),
         ({'x':0,'y':2,'width':10,'height':12},(22,22),(0,0),(2,0),(2,2)),
         ({'x':98,'y':78,'width':2,'height':2},(10,10),(90,70),(0,0),(8,8)),
         ({'x':50,'y':40,'width':1,'height':1},(17,17),(42,32),(0,0),(8,8))]
  for region,want_size,origin,padding,offset in cases:
   source=Image.new('RGBA',(100,80));source.putdata([(x,y,71,(x+y)%256) for y in range(80) for x in range(100)])
   scene=copy.deepcopy(self.scene);scene['nodes'][0]['src']=png(source)
   observed=[]
   def generate(prompt,images,target,**kwargs):
    with Image.open(images[0]) as context:
     observed.append((context.size,context.getpixel(padding),prompt))
     generated=Image.new('RGBA',context.size);generated.putdata([(x,y,220,139) for y in range(context.height) for x in range(context.width)]);generated.save(target)
    return {'actualImageGeneration':True}
   with self.subTest(region=region):
    result=self.run_replace({**self.request,'region':region},scene=scene,generator=generate);actual=pixels(result['nodes'][0]['src'])
    self.assertEqual(observed[0][0],want_size);self.assertEqual(observed[0][1],source.getpixel(origin))
    self.assertEqual(actual.size,(100,80))
    for y in range(80):
     for x in range(100):
      expected=(x-origin[0]+padding[0],y-origin[1]+padding[1],220,139) if region['x']<=x<region['x']+region['width'] and region['y']<=y<region['y']+region['height'] else source.getpixel((x,y))
      self.assertEqual(actual.getpixel((x,y)),expected)
    self.assertIn('"x": '+str(offset[0]),observed[0][2]);self.assertIn('"y": '+str(offset[1]),observed[0][2])
    self.assertEqual(result['source'],self.scene['source']);self.assertEqual(result['originalSource'],self.scene['originalSource'])
 def test_cancelled_context_generation_does_not_publish_any_crop(self):
  stopped=threading.Event();scene=copy.deepcopy(self.scene);scene['nodes'][0]['src']=png(Image.new('RGBA',(100,80),'red'))
  def generate(prompt,images,target,**kwargs):
   with Image.open(images[0]) as context:
    self.assertLess(context.width,100);context.save(target)
   stopped.set();return {'actualImageGeneration':True}
  with self.assertRaises(InterruptedError):self.run_replace(scene=scene,generator=generate,cancelled=stopped.is_set)
 def test_prompt_limit_matches_six_thousand_character_input(self):
  import image_replace
  image_replace.validate_replacement(self.scene,{**self.request,'prompt':'a'*6000})
  with self.assertRaises(ValueError):image_replace.validate_replacement(self.scene,{**self.request,'prompt':'a'*6001})
 def test_fresh_generation_uses_independent_asset_prompt_and_blank_alpha(self):
  import image_replace
  for size,transparent in (((1024,1024),True),((1536,1024),False),((1024,1536),False)):
   scene=generation_scene(size,transparent);original=copy.deepcopy(scene)
   request={'intent':'generate','targetId':'generated-image','region':None,'selection':None,'prompt':'blue vase','reference':{'src':self.source,'region':{'x':1,'y':1,'width':3,'height':2}}}
   def generate(prompt,images,target,**kwargs):
    self.assertIn('全新独立图片',prompt);self.assertIn('仅参考',prompt);self.assertNotIn('用户替换描述',prompt)
    for phrase in ('身份','沿用原对象位置','补边','融入指定范围'):self.assertNotIn(phrase,prompt)
    self.assertIn('透明背景' if transparent else '背景',prompt);self.assertEqual(kwargs['transparent'],transparent)
    self.assertEqual(len(images),2)
    with Image.open(images[1]) as ref:self.assertEqual(ref.size,(3,2))
    Image.new('RGBA',size,(10,20,230,0 if transparent else 255)).save(target);return {'actualImageGeneration':True}
   with self.subTest(size=size),tempfile.TemporaryDirectory() as folder,patch('codex_client.CLIENT.generate',side_effect=generate):
    result=image_replace._process(scene['source'],'new',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
    self.assertEqual(pixels(result['nodes'][0]['src']).size,size);self.assertEqual(result['nodes'][0]['imageReplacement']['intent'],'generate')
    self.assertEqual(scene,original);self.assertEqual(len(result['nodes']),1)
 def test_fresh_generation_rejects_existing_content_or_non_synthetic_scene(self):
  import image_replace
  request={'intent':'generate','targetId':'generated-image','region':None,'selection':None,'prompt':'blue vase','reference':None}
  original=generation_scene();bad=[]
  for changes in ({'groups':[{'id':'g','children':['generated-image']}]},{'edges':[{}]},{'provenance':'generated-image'},{'format':'other'},{'version':1},{'width':1023},{'originalSource':self.source},{'comparisonSource':self.source}):bad.append({**original,**changes})
  for changes in ({'x':1},{'width':1023},{'provenance':'generated-image'},{'mask':{'src':self.source}},{'generationRecord':{'actualImageGeneration':True}}):
   scene=copy.deepcopy(original);scene['nodes'][0].update(changes);bad.append(scene)
  scene=copy.deepcopy(original);scene['nodes'].append({'id':'b','type':'rect'});bad.append(scene)
  bad.append(generation_scene((1024,768)));bad.append(generation_scene((512,512)))
  scene=copy.deepcopy(original);painted=Image.new('RGBA',(1024,1024),'white');painted.putpixel((1,1),(0,0,0,255));src=png(painted)
  scene.update(source=src,originalSource=src,comparisonSource=src);scene['nodes'][0]['src']=src;bad.append(scene)
  for scene in bad:
   with self.subTest(changes=[k for k in scene if scene[k]!=original.get(k)]),self.assertRaises(ValueError):image_replace.validate_replacement(scene,request)
  for changes in ({'region':{'x':0,'y':0,'width':1024,'height':1024}},{'selection':{'type':'polygon','points':[[0,0],[1024,0],[1024,1024],[0,1024]]}}):
   with self.assertRaises(ValueError):image_replace.validate_replacement(original,{**request,**changes})
  with self.assertRaises(ValueError):image_replace.validate_replacement(self.scene,{**self.request,'intent':'generate'})
 def test_unknown_generation_intents_are_rejected_before_model(self):
  for intent in (None,False,True,'replace','fresh-image',{},[]):
   with self.subTest(intent=intent),self.assertRaises(ValueError):self.run_replace({**self.request,'intent':intent})
  self.assertFalse(self.calls)
 def test_hidden_or_archived_target_and_ancestors_never_generate(self):
  for placement in ('node','parent','nested'):
   for flag in ({'visible':False},{'hidden':True},{'versionArchived':True}):
    scene=copy.deepcopy(self.scene)
    if placement=='node':scene['nodes'][0].update(flag)
    elif placement=='parent':scene['groups'][0].update(flag)
    else:scene['groups'].append({'id':'outer','children':['g'],**flag})
    with self.subTest(placement=placement,flag=flag),self.assertRaises(ValueError):self.run_replace(scene=scene)
  self.assertFalse(self.calls)
 def test_invalid_payloads_and_bounds_never_generate(self):
  for delta in ({'targetId':'g'},{'targetId':'b'},{'targetId':'missing'},{'prompt':''},{'prompt':False},{'unknown':1},{'region':{'x':2.2,'y':1,'width':3,'height':2}},{'region':{'x':True,'y':1,'width':3,'height':2}},{'region':{'x':7,'y':1,'width':3,'height':2}},{'region':{'x':0,'y':0,'width':0,'height':2}},{'reference':{'src':'data:image/png;base64,bad','region':None}},{'reference':{'src':self.source,'region':{'x':0,'y':5,'width':1,'height':2}}}):
   with self.subTest(delta=delta),self.assertRaises(ValueError):self.run_replace({**self.request,**delta})
  self.assertFalse(self.calls)
 def test_locked_ancestor_and_layer_rejected_but_single_import_can_replace(self):
  for lock in ('node','parent','nested'):
   scene=copy.deepcopy(self.scene)
   if lock=='node':scene['nodes'][0]['locked']=True
   elif lock=='parent':scene['groups'][0]['locked']=True
   else:scene['groups'].append({'id':'outer','locked':True,'children':['g']})
   with self.subTest(lock=lock),self.assertRaises(ValueError):self.run_replace(scene=scene)
  imported={**self.scene,'provenance':'user-image','groups':[],'nodes':[{'id':'a','name':'import','type':'image','src':self.source,'x':0,'y':0,'width':8,'height':6,'locked':True}]}
  result=self.run_replace(scene=imported);self.assertTrue(result['nodes'][0]['locked'])
  modern=copy.deepcopy(imported);modern.pop('provenance');modern['nodes'][0]['provenance']='imported-source'
  self.assertTrue(self.run_replace(scene=modern)['nodes'][0]['locked'])
  repeated=copy.deepcopy(result);repeated['nodes'].append({**imported['nodes'][0],'id':'old','versionArchived':True,'versionOf':'a','hidden':True,'visible':False})
  self.assertTrue(self.run_replace(scene=repeated)['nodes'][0]['locked'])
  imported['groups']=[{'id':'g','children':['a'],'locked':True}]
  with self.assertRaises(ValueError):self.run_replace(scene=imported)
 def test_cancel_before_or_after_model_never_returns_candidate(self):
  with self.assertRaises(InterruptedError):self.run_replace(cancelled=lambda:True)
  self.assertFalse(self.calls)
  stopped=threading.Event()
  def generate(*args,**kwargs):result=self.generate(*args,**kwargs);stopped.set();return result
  with self.assertRaises(InterruptedError):self.run_replace(cancelled=stopped.is_set,generator=generate)
 def test_missing_real_generation_event_fails(self):
  def generate(*args,**kwargs):result=self.generate(*args,**kwargs);result['actualImageGeneration']=False;return result
  with self.assertRaises(ValueError):self.run_replace(generator=generate)
 def test_malformed_import_metadata_does_not_crash_validation(self):
  imported={**self.scene,'provenance':'user-image','groups':[],'nodes':[{'id':'a','name':'import','type':'image','src':png(Image.new('RGB',(8,6),'blue')),'x':0,'y':0,'width':8,'height':6,'locked':True,'imageReplacement':None}]}
  with self.assertRaises(ValueError):self.run_replace(scene=imported)
 def test_invalid_original_provenance_is_rejected_before_paid_generation(self):
  import image_replace
  source='data:image/png;base64,'+base64.b64encode(b'not an image').decode()
  scene={**self.scene,'originalSource':source}
  with tempfile.TemporaryDirectory() as folder,patch('codex_client.CLIENT.generate',side_effect=self.generate):
   with self.assertRaises(ValueError):image_replace._process(self.source,'fixture',lambda *_:None,lambda:False,source,Path(folder),scene,self.request)
  self.assertFalse(self.calls)
 def test_failed_or_cancelled_generation_cleans_work_and_does_not_publish(self):
  import image_replace
  from session_outputs import SESSIONS
  for error in (RuntimeError('generation failed'),InterruptedError('cancelled')):
   targets=[];count=SESSIONS.count()
   def generate(prompt,images,target,**kwargs):targets.append(Path(target));Image.new('RGBA',(8,6)).save(target);raise error
   with self.subTest(error=type(error).__name__),patch('codex_client.CLIENT.generate',side_effect=generate),patch('codex_client.CLIENT.close',return_value=True) as close:
    with self.assertRaises(type(error)):image_replace.process(self.source,'fixture',lambda *_:None,lambda:False,resume_scene=self.scene,replacement=self.request)
    self.assertFalse(targets[0].parent.exists());self.assertEqual(SESSIONS.count(),count);self.assertTrue(close.called)
 def test_public_process_cleans_files_closes_worker_and_stores_only_candidate_in_ram(self):
  import image_replace
  from session_outputs import SESSIONS
  targets=[]
  def generate(prompt,images,target,**kwargs):targets.append(Path(target));return self.generate(prompt,images,target,**kwargs)
  with patch('codex_client.CLIENT.generate',side_effect=generate),patch('codex_client.CLIENT.close',return_value=True) as close:
   result=image_replace.process(self.source,'fixture',lambda *_:None,lambda:False,resume_scene=self.scene,replacement=self.request)
  try:
   self.assertFalse(targets[0].exists());self.assertTrue(close.called);self.assertIsNone(SESSIONS.get(result['_sessionId'])['psd'])
  finally:SESSIONS.take(result['_sessionId'])

class ReplacementRouteTests(unittest.TestCase):
 setUp=ImageReplaceTests.setUp
 generate=ImageReplaceTests.generate
 def test_health_advertises_replacement_for_browser_capability_check(self):
  import server
  response=server.app.test_client().get('/health',headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
  self.assertEqual(response.status_code,200,response.get_json())
  self.assertIn('replace-image',response.get_json()['jobModes'])
 def test_http_validation_and_dispatch_and_completed_candidate_release(self):
  import server
  client=server.app.test_client();options={'headers':{'X-Shijie-Token':server.TOKEN},'base_url':'http://127.0.0.1:19217'}
  payload={'image':self.source,'mode':'replace-image','resume':self.scene,'replacement':self.request}
  with patch.dict(server.jobs,{},clear=True),patch.object(server.pool,'submit') as submit:
   bad=client.post('/jobs',json={**payload,'replacement':{**self.request,'targetId':'missing'}},**options)
   self.assertEqual(bad.status_code,400);self.assertFalse(submit.called)
   response=client.post('/jobs',json=payload,**options);self.assertEqual(response.status_code,202,response.get_json())
   args,kwargs=submit.call_args
   self.assertEqual(kwargs['replacement'],self.request)
   ident=response.get_json()['id']
   with patch('codex_client.CLIENT.generate',side_effect=self.generate),patch('codex_client.CLIENT.close',return_value=True):server.run(*args[1:],**kwargs)
   self.assertEqual(server.jobs[ident]['status'],'completed',server.jobs[ident])
   from session_outputs import SESSIONS
   session=server.jobs[ident]['sessionId'];self.assertIsNotNone(SESSIONS.get(session))
   client.delete('/jobs/'+ident,**options);self.assertIsNone(SESSIONS.get(session))

if __name__=='__main__':unittest.main()
