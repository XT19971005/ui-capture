import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class AssistantSplitTests(unittest.TestCase):
 def test_mixed_split_background_uses_opaque_generation_not_asset_expansion(self):
  import assistant_split as s
  body=self.body();body['layers']=[{'name':'纯净场景底稿','instruction':'去掉所有独立前景，补齐纯净背景','assetKind':'background','box':{'x':0,'y':0,'width':100,'height':100}},body['layers'][0]]
  calls=[]
  def generate(prompt,images,target,**kw):
   self.assertFalse(kw['transparent']);self.assertIn('勋章',prompt);self.assertNotIn('只补UI遮挡区域',prompt);calls.append('background');Image.new('RGB',(100,100),'blue').save(target);return {'actualImageGeneration':True}
  def extract(source,node,*args):
   calls.append('asset');return {**node,'src':body['image'],'provenance':'codex-image-generation','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),patch('incremental_assets.extract_once',side_effect=extract):result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual(calls,['background','asset']);self.assertEqual([n['assetKind'] for n in result['nodes']],['background','complete-asset']);self.assertEqual(result['source'],body['image'])

 def test_outside_completion_box_is_normalized_to_visible_reference_not_rejected(self):
  import hashlib,assistant_split as s
  body=self.body();body['annotations']={'version':1,'width':100,'height':100,'sourceHash':hashlib.sha256(body['image'].encode()).hexdigest(),'allowExpand':True,'items':[]}
  body['layers'][0]['box']={'x':-70,'y':-10,'width':150,'height':160}
  result=s.validate(body)
  self.assertEqual(result['layers'][0]['box'],{'x':0,'y':0,'width':80,'height':100})
  self.assertIn('旧框不是裁切边界',result['layers'][0]['instruction'])
  self.assertEqual(body['layers'][0]['box']['x'],-70)

 def test_outside_box_without_source_overlap_still_rejects(self):
  import hashlib,assistant_split as s
  body=self.body();body['annotations']={'version':1,'width':100,'height':100,'sourceHash':hashlib.sha256(body['image'].encode()).hexdigest(),'allowExpand':True,'items':[]};body['layers'][0]['box']={'x':-500,'y':0,'width':100,'height':100}
  with self.assertRaises(ValueError):s.validate(body)

 def test_background_wrong_aspect_is_retained_for_review_without_stretch(self):
  import assistant_split as s
  from image_replace import _image
  body=self.body();body['backgroundOnly']=True;body['layers']=[{'name':'背景','instruction':'完整背景','box':{'x':0,'y':0,'width':100,'height':100}}]
  def generate(prompt,images,target,**kw):Image.new('RGB',(100,150),'blue').save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):r=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  n=r['nodes'][0];self.assertTrue(r['_partial']);self.assertTrue(n['positionReviewRequired']);self.assertAlmostEqual(n['width']/n['height'],2/3)
  with _image(n['src']) as im:self.assertEqual(im.size,(100,150))
 def test_marks_reach_extraction_as_separate_reference_without_changing_source(self):
  import hashlib,assistant_split as s
  body=self.body();body['annotations']={'version':1,'width':100,'height':100,'sourceHash':hashlib.sha256(body['image'].encode()).hexdigest(),'items':[{'color':'#ffdf24','label':'后面勋章','strokes':[[[10,30],[50,5],[90,30],[50,95],[10,30]]]}]}
  def extract(source,node,assets,structure,*args):
   self.assertTrue((structure/'用户原画标注.png').is_file());self.assertIn('后面勋章',(structure/'用户原画标注.json').read_text('utf8'));return {**node,'src':body['image'],'provenance':'codex-image-generation','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=extract):s.generate(body,Path(folder),lambda:False,lambda *_:None)
 def body(self):
  source=png(Image.new('RGBA',(100,100),'green'))
  layers=[{'name':n,'instruction':'独立完整提取'+n,'box':{'x':10,'y':10,'width':80,'height':80}} for n in ('勋章','鱼','特级大师')]
  return {'image':source,'width':100,'height':100,'title':'三层拆分','layers':layers}
 def test_only_requested_three_layers_back_to_front_no_background_no_source_node(self):
  import assistant_split as s
  body=self.body();before=copy.deepcopy(body);calls=[]
  def extract(source,node,*args):
   calls.append(copy.deepcopy(node));return {**node,'src':png(Image.new('RGBA',(80,80),(255,0,0,100))),'provenance':'generated-complete-asset','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=extract):result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual([n['name'] for n in result['nodes']],['勋章','鱼','特级大师']);self.assertEqual(len(calls),3);self.assertIsNone(result['background']);self.assertEqual(result['recognition']['extractionStatus'],'COMPLETED');self.assertEqual(body,before)
  self.assertGreaterEqual(result['recognition']['timing']['elapsedMs'],0);self.assertIn('completedAt',result['recognition']['timing'])
 def test_no_fallback_crop_or_fake_complete(self):
  import assistant_split as s
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=lambda source,node,*args:{**node,'provenance':'source-crop-fallback'}):
   with self.assertRaises(ValueError):s.generate(self.body(),Path(folder),lambda:False,lambda *_:None)
 def test_invalid_boxes_and_too_many_layers_never_submit(self):
  import assistant_split as s
  for change in ({'layers':[]},{'layers':self.body()['layers']*8},{'width':float('nan')}):
   with self.subTest(change=change),self.assertRaises(ValueError):s.validate({**self.body(),**change})
 def test_cancel_before_next_layer_prevents_more_generation(self):
  import assistant_split as s
  calls=[]
  def extract(source,node,*args):calls.append(node);return {**node,'provenance':'generated-complete-asset','src':'test','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=extract):
   with self.assertRaises(InterruptedError):s.generate(self.body(),Path(folder),lambda:bool(calls),lambda *_:None)
  self.assertEqual(len(calls),1)

 def test_background_removes_ui_without_transparent_extraction(self):
  import assistant_split as s
  body=self.body();body['backgroundOnly']=True;body['layers']=[{'name':'荷塘背景','instruction':'去掉全部UI，保留鱼和荷花并补齐遮挡','box':{'x':0,'y':0,'width':100,'height':100}}]
  def generate(prompt,images,target,**kw):
   self.assertFalse(kw['transparent']);self.assertIn('去掉全部UI',prompt);self.assertIn('禁止自动提亮',prompt)
   Image.new('RGB',(100,100),'green').save(target)
   return {'actualImageGeneration':True,'provider':'aimake'}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate),patch('incremental_assets.extract_once',side_effect=AssertionError('must not extract transparent')):
   result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual(len(result['nodes']),1);self.assertEqual(result['nodes'][0]['assetKind'],'background');self.assertEqual(result['nodes'][0]['width'],100)

 def test_outpaint_keeps_center_pixels_and_returns_exact_canvas(self):
  import assistant_split as s
  body=self.body();body.update(backgroundOnly=True,outpaint=True)
  body['layers']=[{'name':'荷塘扩建背景','instruction':'左右不动，上下扩建','box':{'x':0,'y':0,'width':100,'height':160}}]
  def generate(prompt,images,target,**kw):
   self.assertIn('上下扩建',prompt);Image.new('RGB',(120,192),'blue').save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual((result['width'],result['height']),(100,160))
  from image_replace import _image
  with _image(result['nodes'][0]['src']) as im:
   self.assertEqual(im.getpixel((50,30)),(0,128,0,255));self.assertEqual(im.getpixel((50,0)),(0,0,255,255))

 def test_transparent_source_rejected_before_outpaint_payment(self):
  import assistant_split as s
  body=self.body();body.update(backgroundOnly=True,outpaint=True,image=png(Image.new('RGBA',(100,100),(0,0,0,0))))
  body['layers']=[{'name':'扩建背景','instruction':'上下扩建','box':{'x':0,'y':0,'width':100,'height':160}}]
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate') as generate:
   with self.assertRaisesRegex(ValueError,'不透明背景'):s.generate(body,Path(folder),lambda:False,lambda *_:None)
   generate.assert_not_called()

 def test_remove_ui_and_expand_is_one_generation_without_pasting_ui_back(self):
  import assistant_split as s
  body=self.body();body['backgroundOnly']=True
  body['layers']=[{'name':'扩建荷塘背景','instruction':'去掉全部UI并上下扩建，左右不动','box':{'x':0,'y':0,'width':100,'height':160}}]
  calls=[]
  def generate(prompt,images,target,**kw):
   calls.append(prompt);self.assertIn('同时',prompt);self.assertFalse(kw['transparent']);Image.new('RGB',(100,160),'blue').save(target);return {'actualImageGeneration':True}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=generate):result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual(len(calls),1);self.assertEqual((result['width'],result['height']),(100,160))
  from image_replace import _image
  with _image(result['nodes'][0]['src']) as im:self.assertEqual(im.getpixel((50,80)),(0,0,255,255))

 def test_later_failure_preserves_completed_layers_and_pending_plan(self):
  import assistant_split as s
  body=self.body();calls=[];snapshots=[]
  def extract(source,node,*args):
   calls.append(node['name'])
   if len(calls)==2:raise ValueError('第二层失败')
   return {**node,'src':body['image'],'provenance':'codex-image-generation','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=extract):
   with self.assertRaises(ValueError) as caught:s.generate(body,Path(folder),lambda:False,lambda *_:None,on_scene=snapshots.append)
  self.assertEqual(len(calls),2);self.assertEqual(len(snapshots),1)
  partial=caught.exception.partial;self.assertTrue(partial['_partial']);self.assertEqual([n['name'] for n in partial['nodes']],['勋章'])
  self.assertEqual(partial['recognition']['pendingLayers'],body['layers'][1:]);self.assertEqual(partial['recognition']['extractionStatus'],'INCOMPLETE')

 def test_edge_risk_is_retained_as_incomplete_not_a_completed_split(self):
  import assistant_split as s
  body=self.body()
  def extract(source,node,*args):return {**node,'src':body['image'],'provenance':'codex-image-generation','boundaryReviewRequired':node['name']=='勋章','generationRecord':{'actualImageGeneration':True}}
  with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=extract):result=s.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual(len(result['nodes']),3);self.assertTrue(result['_partial']);self.assertEqual(result['recognition']['extractionStatus'],'INCOMPLETE');self.assertEqual([l['name'] for l in result['recognition']['pendingLayers']],['勋章'])
