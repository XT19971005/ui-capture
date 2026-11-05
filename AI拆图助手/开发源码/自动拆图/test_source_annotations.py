import copy,hashlib,tempfile,unittest
from pathlib import Path
from PIL import Image
from engine import png

class SourceAnnotationTests(unittest.TestCase):
 def fixture(self):
  source=png(Image.new('RGBA',(80,100),(80,140,120,255)))
  state={'version':1,'width':80,'height':100,'sourceHash':hashlib.sha256(source.encode()).hexdigest(),'items':[{'color':'#ffdf24','label':'后方完整勋章','strokes':[[[10,30],[40,5],[70,30],[40,90],[10,30]]]}]}
  return source,state
 def test_annotation_keeps_original_and_renders_an_extra_reference(self):
  from source_annotations import validate,render
  source,state=self.fixture();before=copy.deepcopy(state)
  self.assertEqual(validate(state,source,80,100),state)
  with tempfile.TemporaryDirectory() as folder:
   original=Path(folder)/'original.png';Image.new('RGB',(80,100),(80,140,120)).save(original);raw=original.read_bytes()
   reference=render(state,original,Path(folder)/'guide.png')
   self.assertEqual(original.read_bytes(),raw)
   with Image.open(reference) as image:self.assertNotEqual(image.convert('RGB').getpixel((40,6)),(80,140,120))
  self.assertEqual(state,before)
 def test_rejects_wrong_source_dimensions_color_and_nonfinite_points(self):
  from source_annotations import validate
  source,state=self.fixture()
  cases=[{**state,'sourceHash':'0'*64},{**state,'width':81},{**state,'items':[{'color':'red','label':'x','strokes':[[[1,2],[3,4]]]}]},{**state,'items':[{'color':'#ffdf24','label':'x','strokes':[[[1,float('nan')],[3,4]]]}]}]
  for value in cases:
   with self.subTest(value=value),self.assertRaises(ValueError):validate(value,source,80,100)
 def test_empty_and_oversized_markings_are_not_model_references(self):
  from source_annotations import validate
  source,state=self.fixture()
  self.assertIsNone(validate(None,source,80,100))
  self.assertEqual(validate({**state,'items':[]},source,80,100)['items'],[])
  with self.assertRaises(ValueError):validate({**state,'items':state['items']*7},source,80,100)
 def test_actual_extractor_gets_crop_full_clean_original_and_guide(self):
  from unittest.mock import patch
  from source_annotations import install
  from workflow_assets import complete_asset
  source,state=self.fixture()
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);assets=home/'1_过程/01_素材';structure=home/'1_过程/02_结构';assets.mkdir(parents=True);structure.mkdir();original=home/'clean.png';Image.new('RGB',(80,100),(80,140,120)).save(original);raw=original.read_bytes();install(state,original,structure)
   def generate(prompt,images,target,**kwargs):
    self.assertEqual(len(images),3);self.assertEqual(images[1],original);self.assertIn('完整干净原图',prompt);self.assertIn('后方完整勋章',prompt)
    im=Image.new('RGBA',(80,100));im.paste((255,0,0,255),(10,10,70,90));im.save(target);return {'actualImageGeneration':True,'transparent':True}
   with patch('image_provider.CLIENT.generate',side_effect=generate):complete_asset(original,{'id':'qa','name':'勋章','type':'image','x':10,'y':10,'width':60,'height':80},assets,structure,lambda:False)
   self.assertEqual(original.read_bytes(),raw)
 def test_assistant_receives_clean_image_and_separate_guides_and_names(self):
  from unittest.mock import patch
  import free_assistant
  source,state=self.fixture();body={'image':source,'scene':{'width':80,'height':100,'nodes':[]},'selectedIds':[],'messages':[{'role':'user','content':'只讨论，黄色是什么'}],'provider':'tygpt','model':'vision','annotations':state}
  result={'reply':'黄色标出后方勋章','action':'discuss','instruction':'','targetIds':[],'reference':'original','name':'','layers':[]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=result) as analyze:
   free_assistant.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertEqual(len(analyze.call_args.args[1]),2);self.assertIn('后方完整勋章',analyze.call_args.args[0]);self.assertIn('不是硬裁剪蒙版',analyze.call_args.args[0])

class ExtendedColorTests(SourceAnnotationTests):
 def test_custom_hex_colors_and_more_than_six_objects(self):
  from source_annotations import validate
  source,state=self.fixture()
  state['items']=[{'color':'#%06x'%i,'label':'对象'+str(i),'strokes':[[[1,2],[3,4]]]} for i in range(24)]
  self.assertEqual(len(validate(state,source,80,100)['items']),24)
  state['items'][0]['color']='url(x)'
  with self.assertRaises(ValueError):validate(state,source,80,100)

class AnnotationPurposeTests(unittest.TestCase):
 def test_purpose_and_preserve_roundtrip_summary(self):
  from source_annotations import validate,summary
  source,state=SourceAnnotationTests().fixture();state['items'][0]['purpose']='remove';state['preserve']='保留右胳膊，补齐遮挡'
  result=validate(state,source,80,100)
  self.assertEqual(summary(result)[0]['purpose'],'remove')
  self.assertEqual(result['preserve'],state['preserve'])
  state['items'][0]['purpose']='erase-everything'
  with self.assertRaises(ValueError):validate(state,source,80,100)
