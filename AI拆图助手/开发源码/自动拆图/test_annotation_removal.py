import copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png
import image_replace

class RemovalTests(unittest.TestCase):
 def fixture(self):
  im=Image.new('RGBA',(80,100));im.paste((100,150,80,255),(5,5,75,95));src=png(im)
  marks={'version':1,'width':80,'height':100,'sourceHash':hashlib.sha256(src.encode()).hexdigest(),'preserve':'右胳膊完整，补齐遮挡','items':[{'color':'#ffdf24','label':'左胳膊','purpose':'remove','strokes':[[[5,5],[35,10],[35,90],[5,5]]]},{'color':'#39d8ff','label':'右胳膊','purpose':'keep','strokes':[[[45,5],[75,10],[75,90],[45,5]]]}]}
  scene={'format':'shijie-scene','version':2,'width':80,'height':100,'title':'测试手臂','provenance':'user-image','source':src,'comparisonSource':src,'originalSource':src,'nodes':[{'id':'raw','name':'原图','type':'image','src':src,'x':0,'y':0,'width':80,'height':100,'locked':True,'provenance':'imported-source'}],'groups':[],'edges':[],'_sourceAnnotations':marks}
  request={'targetId':'raw','task':'remove','annotations':marks,'prompt':'删除左胳膊，保留右胳膊完整'}
  return scene,request
 def test_validated_semantic_removal_sends_clean_and_separate_aligned_guide(self):
  scene,request=self.fixture();before=copy.deepcopy(scene)
  def generate(prompt,images,target,**kw):
   self.assertEqual(len(images),2);self.assertFalse(kw['allow_identity_change']);self.assertTrue(kw['transparent']);self.assertIn('remove',prompt);self.assertIn('右胳膊完整',prompt);self.assertIn('不是硬裁剪蒙版',prompt)
   with Image.open(images[0]) as clean,Image.open(images[1]) as guide:self.assertEqual(clean.size,guide.size);self.assertNotEqual(clean.tobytes(),guide.tobytes())
   im=Image.new('RGBA',(100,100));im.paste((100,150,80,255),(55,5,85,95));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  self.assertEqual(scene,before);self.assertNotEqual(result['nodes'][0]['src'],scene['source']);self.assertEqual(result['nodes'][0]['width'],80)
 def test_rejects_missing_delete_wrong_source_and_hard_region(self):
  scene,request=self.fixture()
  for mutate in ('missing','keep','hash','region'):
   value=copy.deepcopy(request)
   if mutate=='missing':value.pop('annotations')
   if mutate=='keep':value['annotations']['items'][0]['purpose']='keep'
   if mutate=='hash':value['annotations']['sourceHash']='0'*64
   if mutate=='region':value['region']={'x':0,'y':0,'width':20,'height':20}
   with self.subTest(mutate=mutate),self.assertRaises(ValueError):image_replace.validate_replacement(scene,value)
 def test_rejects_fake_transparency_without_mutating_source(self):
  scene,request=self.fixture();before=copy.deepcopy(scene)
  def generate(prompt,images,target,**kw):Image.new('RGB',(100,100),'white').save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'透明通道'):image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  self.assertEqual(scene,before)

 def test_transparent_padding_cannot_hide_an_opaque_final_crop(self):
  scene,request=self.fixture()
  def generate(prompt,images,target,**kw):
   im=Image.new('RGBA',(100,100));im.paste((80,120,160,255),(10,0,90,100));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'实际内容区'):image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)

 def test_expanded_removal_preserves_scale_and_returns_new_geometry(self):
  scene,request=self.fixture();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   self.assertIn('禁止缩小主体',prompt);self.assertTrue(kw['transparent'])
   im=Image.new('RGBA',(150,150));im.paste((100,150,80,255),(25,10,125,140));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
  n=result['nodes'][0];self.assertEqual((n['x'],n['y'],n['width'],n['height']),(-20,-25,120,150));self.assertEqual(n['imageReplacement']['expansion']['inputWidth'],80)
 def test_layer_annotations_are_bound_to_selected_source_not_whole_scene(self):
  scene,request=self.fixture();scene['nodes'][0].update(x=200,y=300,width=40,height=50,locked=False)
  self.assertEqual(image_replace.validate_replacement(scene,request)['annotations']['sourceHash'],request['annotations']['sourceHash'])

 def test_expanded_content_in_aspect_padding_is_not_silently_cropped(self):
  scene,request=self.fixture();request['annotations']['allowExpand']=True
  def generate(prompt,images,target,**kw):
   im=Image.new('RGBA',(150,150));im.paste((100,150,80,255),(25,10,125,140));im.paste((100,150,80,255),(1,1,5,5));im.save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),self.assertRaisesRegex(ValueError,'配比补边'):image_replace._process(scene['source'],'测试',lambda *_:None,lambda:False,scene['source'],Path(folder),scene,request)
