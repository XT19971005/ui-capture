import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from expansion_geometry import margins
from expanded_assets import extract
class ExpandedTests(unittest.TestCase):
 def test_faint_edge_glow_is_retained_without_false_incomplete_shape(self):
  from expanded_assets import register_asset
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'glow.png';im=Image.new('RGBA',(100,100));im.paste((200,220,255,255),(20,20,80,80));im.putpixel((0,50),(200,220,255,1));im.save(path)
   result=register_asset(path,100,(0,0));self.assertFalse(result['boundaryReviewRequired'])
   import base64,io
   with Image.open(io.BytesIO(base64.b64decode(result['src'].split(',')[1]))) as saved:self.assertEqual(saved.getpixel((0,50)),(200,220,255,1))

 def test_large_original_keeps_its_pixels_and_uses_safe_margins(self):
  mx,my=margins(2048,2048);self.assertGreater(mx,0);self.assertLessEqual((2048+2*mx)*(2048+2*my),36000000)
 def test_asset_can_extend_beyond_old_box_without_being_fitted_back(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   def generate(prompt,images,target,**kwargs):
    self.assertIn('不压缩',prompt);im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(25,10,125,140));im.save(target);return {'actualImageGeneration':True}
   with patch('semantic_registration.calibrate_semantic',side_effect=ValueError('受控测试不调用模型')),patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'完整袖子','extractionBrief':'保留完整袖子','x':10,'y':20,'width':30,'height':40},p,lambda:False,lambda *_:None)
   # Independent HD composition changes the provisional world transform,
   # while the entire native returned bitmap must survive.
   self.assertGreater(n['width'],30);self.assertGreater(n['height'],40)
   self.assertTrue(n['positionReviewRequired'])
   with Image.open(p/'layer_完整扩展.png') as saved:self.assertEqual(saved.size,(150,150))
 def test_clipped_outer_edge_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   def generate(prompt,images,target,**kwargs):
    im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(15,0,100,150));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'袖子','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertTrue(n['boundaryReviewRequired']);self.assertIn('可能不完整',n['reviewIssue'])

 def test_content_in_square_padding_expands_registration_without_losing_pixels(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(100,80)).save(source)
   def generate(prompt,images,target,**kwargs):
    im=Image.new('RGBA',(150,150));im.paste((80,100,120,255),(10,5,140,145));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'完整武器','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertTrue(n['positionReviewRequired'])
   self.assertAlmostEqual(n['width']/150,n['height']/150)
   self.assertEqual(n['registration']['rawWidth'],150)
   with Image.open(p/'layer_完整扩展.png') as im:
    self.assertEqual(im.getchannel('A').getbbox(),(10,5,140,145))
    self.assertEqual(sum(im.getchannel('A').getdata()),130*140*255)

 def test_generated_reference_and_full_visible_result_stay_under_pixel_limit(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(2048,1143)).save(source)
   def generate(prompt,images,target,**kwargs):
    with Image.open(images[0]) as ref:side=ref.width
    self.assertLessEqual(side*side,36000000)
    im=Image.new('RGBA',(side,side));im.paste((80,100,120,255),(50,50,side-50,side-50));im.save(target);return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):n=extract(source,{'id':'layer','name':'大素材','extractionBrief':'完整'},p,lambda:False,lambda *_:None)
   self.assertLessEqual(n['width']*n['height'],36000000)

 def test_partial_geometry_is_rejected_before_generation(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(80,100)).save(source)
   with patch('image_provider.CLIENT.generate') as generate,self.assertRaisesRegex(ValueError,'完整提供'):
    extract(source,{'id':'partial','name':'主体','extractionBrief':'完整','x':10},p,lambda:False,None)
   generate.assert_not_called()

 def test_independent_reference_follows_horizontal_vertical_square_and_extreme_shapes(self):
  from asset_resolution import prepare_reference,resolution_prompt
  cases=[((600,200),(1536,512)),((200,600),(512,1536)),((400,400),(1536,1536)),((1000,20),(1536,512)),((20,1000),(512,1536))]
  with tempfile.TemporaryDirectory() as folder:
   for dimensions,expected in cases:
    path=Path(folder)/'reference.png'
    frame=prepare_reference(Image.new('RGBA',dimensions,(20,40,60,255)),{},path)
    self.assertEqual((frame['referenceWidth'],frame['referenceHeight']),expected)
    self.assertIn(str(expected[0])+'×'+str(expected[1]),resolution_prompt(frame))
    with Image.open(path) as reference:
     self.assertEqual(reference.size,expected);visible=reference.getchannel('A').getbbox()
     sx=(visible[2]-visible[0])/dimensions[0];sy=(visible[3]-visible[1])/dimensions[1]
     self.assertLess(abs(sx-sy),max(1/dimensions[0],1/dimensions[1]))
    self.assertAlmostEqual(frame['sourceCanvasSize'][0],expected[0]*frame['referenceToSourceScale'])
    self.assertAlmostEqual(frame['sourceCanvasSize'][1],expected[1]*frame['referenceToSourceScale'])

 def test_rectangular_native_return_is_preserved_and_requested_dimensions_registered(self):
  import base64,io
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(600,200),(20,40,60,255)).save(source);returned=[]
   def generate(prompt,images,target,**kwargs):
    self.assertIn('1536×512',prompt)
    with Image.open(images[0]) as reference:self.assertEqual(reference.size,(1536,512))
    image=Image.new('RGBA',(1800,900));image.paste((70,90,110,255),(100,100,1700,800));image.save(target);returned.append(Path(target).read_bytes())
    return {'actualImageGeneration':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):
    node=extract(source,{'id':'rectangle','name':'横向主体','extractionBrief':'完整'},p,lambda:False,None)
   self.assertEqual(base64.b64decode(node['src'].split(',')[1]),returned[0])
   with Image.open(io.BytesIO(returned[0])) as saved:self.assertEqual(saved.size,(1800,900))
   request=node['generationRecord']['independentAssetRequest']
   self.assertEqual((request['referenceWidth'],request['referenceHeight']),(1536,512))
   self.assertEqual(node['assetResolution']['subjectLongEdge'],1600)

 def test_model_enum_ratios_are_exact_and_pass_nano_parameter_validation(self):
  from asset_resolution import prepare_reference
  from image_provider import generation_input
  schema={'input':{'type':'object','properties':{'prompt':{'type':'string'},'input_images':{'type':'array','maxItems':3},'aspect_ratio':{'enum':['3:2','16:9','21:9']}},'required':['prompt','input_images','aspect_ratio']}}
  with tempfile.TemporaryDirectory() as folder:
   for dimensions,expected in [((1370,1000),'3:2'),((1780,1000),'16:9'),((2330,1000),'21:9')]:
    path=Path(folder)/'reference.png';frame=prepare_reference(Image.new('RGBA',dimensions),{},path,allowed_ratios=schema['input']['properties']['aspect_ratio']['enum'])
    width,height=frame['referenceWidth'],frame['referenceHeight'];a,b=map(int,expected.split(':'))
    self.assertEqual(width*b,height*a);self.assertEqual(width%16,0);self.assertEqual(height%16,0)
    self.assertGreaterEqual(max(width,height),1280)
    payload=generation_input('nano-banana-2','controlled reference prompt',[path],['https://reference.invalid/image.png'],schema=schema)
    self.assertEqual(payload['aspect_ratio'],expected)

 def test_aimake_uses_selected_model_cached_schema_before_reference_layout(self):
  from image_provider import generation_input
  schema={'input':{'type':'object','properties':{'prompt':{'type':'string'},'input_images':{'type':'array','maxItems':3},'aspect_ratio':{'enum':['16:9']}},'required':['prompt','input_images','aspect_ratio']}}
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(1370,1000),(20,40,60,255)).save(source)
   def generate(prompt,images,target,**kwargs):
    payload=generation_input('nano-banana-2',prompt,images,['https://reference.invalid/'+str(i)+'.png' for i in range(len(images))],schema=schema)
    self.assertEqual(payload['aspect_ratio'],'16:9')
    image=Image.new('RGBA',(1536,864));image.paste((50,70,90,255),(100,100,1400,760));image.save(target)
    return {'actualImageGeneration':True}
   with patch('image_provider.settings',return_value={'provider':'aimake','model':'nano-banana-2'}),patch('image_provider.model_schema',return_value=schema) as read_schema,patch('image_provider.CLIENT.generate',side_effect=generate):
    node=extract(source,{'id':'enum','name':'主体','extractionBrief':'完整'},p,lambda:False,None)
   read_schema.assert_called_once_with('nano-banana-2')
   request=node['generationRecord']['independentAssetRequest'];self.assertEqual(request['referenceWidth']*9,request['referenceHeight']*16)

 def test_nano_small_context_and_repair_are_padded_without_resampling_or_mutating_sources(self):
  import base64,hashlib
  from image_provider import generation_input
  schema={'input':{'properties':{'prompt':{'type':'string'},'input_images':{'type':'array','maxItems':3},'aspect_ratio':{'enum':['4:3']}},'required':['prompt','input_images','aspect_ratio']}}
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);source=p/'source.png';Image.new('RGBA',(112,82),(20,40,60,255)).save(source);original=source.read_bytes();digest=hashlib.sha256(original).hexdigest()
   layer={'id':'small','name':'主体','extractionBrief':'完整','_repairSource':'data:image/png;base64,'+base64.b64encode(original).decode()}
   def generate(prompt,images,target,**kwargs):
    self.assertEqual(len(images),3)
    generation_input('nano-banana-2',prompt,images,['https://reference.invalid/'+str(i)+'.png' for i in range(3)],schema=schema)
    for reference in images[1:]:
     with Image.open(reference) as image:
      self.assertEqual(image.size,(300,300));self.assertEqual(image.getchannel('A').getbbox(),(94,109,206,191));self.assertEqual(image.getpixel((94,109)),(20,40,60,255))
    image=Image.new('RGBA',(1536,1024));image.paste((50,70,90,255),(100,100,1400,900));image.save(target)
    return {'actualImageGeneration':True}
   with patch('image_provider.settings',return_value={'provider':'aimake','model':'nano-banana-2'}),patch('image_provider.model_schema',return_value=schema),patch('image_provider.CLIENT.generate',side_effect=generate) as calls:
    node=extract(source,layer,p,lambda:False,None)
   self.assertEqual(calls.call_count,1);self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
   self.assertEqual(base64.b64decode(node['src'].split(',')[1]),(p/'small_完整扩展.png').read_bytes());self.assertFalse(list(p.glob('*参考.png')))
   with patch('image_provider.settings',return_value={'provider':'aimake','model':'nano-banana-2'}),patch('image_provider.model_schema',return_value=schema),patch('image_provider.CLIENT.generate',side_effect=ValueError('controlled failed upload')) as calls:
    with self.assertRaisesRegex(ValueError,'controlled failed upload'):extract(source,layer,p,lambda:False,None)
   self.assertEqual(calls.call_count,1);self.assertFalse(list(p.glob('*参考.png')));self.assertEqual(source.read_bytes(),original)
