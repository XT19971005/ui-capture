"""Local counterexamples: native fonts, exact stacking and explicit entity identity."""
import unittest,copy,json,subprocess,os
from unittest.mock import patch
from pathlib import Path
import numpy as np
from PIL import Image,ImageFont,ImageDraw
import engine,planner,text_style

def text_row(text,box):
 x,y,r,b=box
 return {'id':'copy','text':text,'bbox':list(box),'quad':[[x,y],[r,y],[r,b],[x,b]],'confidence':1}

class SourceTextFidelity(unittest.TestCase):
 def test_majority_dark_ink_does_not_invert_a_tight_heavy_title(self):
  text='LIFE ATTITUDE';font=ImageFont.truetype('C:/Windows/Fonts/impact.ttf',70);b=font.getbbox(text)
  im=Image.new('RGB',(b[2]-b[0]+2,b[3]-b[1]+2),'white')
  ImageDraw.Draw(im).text((1-b[0],1-b[1]),text,font=font,fill='black')
  rgb=np.array(im);self.assertGreater(np.mean(np.min(rgb,axis=2)<80),.55)
  fitted=text_style.estimate(rgb,text)
  self.assertIsNotNone(fitted);self.assertEqual(fitted['fontFamily'],'Impact')
  self.assertAlmostEqual(fitted['fontSize'],70,delta=2);self.assertFalse(fitted['fitWidth'])

 def test_real_user_tall_narrow_title_does_not_fall_back_to_flat_default(self):
  source=Path('C:/Users/tuyou/AppData/Local/Temp/codex-clipboard-55a3c7dd-82ce-49c7-bfc3-8ff00f2bf2bf.png')
  if not source.is_file():self.skipTest('original user regression ROI unavailable')
  image=np.array(Image.open(source).convert('RGB'))
  fitted=text_style.estimate(image[74:152,73:484],'LIFE ATTITUDE')
  self.assertIsNotNone(fitted,'real tall condensed heading must retain observed glyph height')
  self.assertIn(fitted['fontFamily'],('Impact','Arial Narrow','Haettenschweiler'))
  self.assertFalse(fitted['fitWidth']);self.assertTrue(fitted['fontMatchApproximate'])
  self.assertGreaterEqual(fitted['fontSize'],70)
  self.assertLess(fitted['nativeDensityError'],.15,'do not settle for a visibly wider/lighter approximation when a closer installed condensed font exists')
  nodes,_=engine.text_nodes([text_row('LIFE ATTITUDE',[73,74,484,152])],image,set())
  self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],'LIFE ATTITUDE')
  self.assertIn('nativeDensityError',nodes[0]);self.assertTrue(nodes[0]['fontMatchApproximate'])

 def test_unmatched_plain_small_text_never_gets_a_contrast_based_stroke(self):
  rgb=np.full((32,60,3),255,np.uint8)
  noise=np.random.default_rng(7).random((20,44))<.3;rgb[6:26,8:52][noise]=0
  # Unknown glyph is deliberately not a supported font match; plain is safe.
  nodes,_=engine.text_nodes([text_row('未识别',[3,2,56,29])],rgb,set())
  self.assertEqual(nodes[0]['strokeWidth'],0)
  self.assertNotIn('layerStyle',nodes[0])

 def test_impact_tall_english_uses_real_font_without_horizontal_stretch(self):
  text='LIFE ATTITUDE';font=ImageFont.truetype('C:/Windows/Fonts/impact.ttf',60)
  b=font.getbbox(text);im=Image.new('RGB',(b[2]-b[0]+20,b[3]-b[1]+14),'white')
  ImageDraw.Draw(im).text((10-b[0],7-b[1]),text,font=font,fill='#202020')
  fitted=text_style.estimate(np.array(im),text)
  self.assertIsNotNone(fitted);self.assertEqual(fitted['fontFamily'],'Impact')
  self.assertFalse(fitted['fitWidth']);self.assertAlmostEqual(fitted['fontSize'],60,delta=2)
  self.assertEqual(fitted['offsetY'],7)

 def test_copyright_uses_glyph_height_not_padded_ocr_box(self):
  text='Copyright 2026. All rights reserved.';font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
  im=Image.new('RGB',(360,60),'white');ImageDraw.Draw(im).text((8,14),text,font=font,fill='#333333')
  fitted=text_style.estimate(np.array(im),text)
  self.assertIsNotNone(fitted);self.assertAlmostEqual(fitted['fontSize'],18,delta=2)
  self.assertFalse(fitted['fitWidth']);self.assertEqual(fitted['strokeWidth'],0)

 def test_existing_sentence_breaks_remain_in_one_editable_native_text(self):
  text='LIFE\nATTITUDE';font=ImageFont.truetype('C:/Windows/Fonts/impact.ttf',42)
  im=Image.new('RGB',(190,120),'white');ImageDraw.Draw(im).multiline_text((8,5),text,font=font,spacing=8,fill='#222222')
  nodes,_=engine.text_nodes([text_row(text,[0,0,190,120])],np.array(im),set())
  self.assertEqual(len(nodes),1);self.assertEqual(nodes[0]['text'],text)
  self.assertFalse(nodes[0].get('fitWidth',False));self.assertEqual(nodes[0]['strokeWidth'],0)

class EntityFidelity(unittest.TestCase):
 def asset(self,ident,kind,box,entity='',z=None):
  a={'id':ident,'name':ident,'kind':kind,'box':box,'entityId':entity,'parent':None}
  if z is not None:a['z_index']=z
  return a
 def test_nonhuman_character_cushion_and_held_cup_merge_only_by_explicit_identity(self):
  a=[self.asset('dragon','decoration',[20,10,70,65],'dragon',4),self.asset('cushion','panel',[15,55,80,82],'dragon',3),self.asset('held-cup','icon',[63,28,84,48],'dragon',5),self.asset('loose-cup','icon',[68,30,90,50],'loose',6)]
  result=planner.complete_entities(a)
  self.assertEqual(len(result),2)
  self.assertEqual(result[0]['id'],'dragon');self.assertEqual(result[0]['box'],[15,10,84,82])
  self.assertEqual(result[0]['entityParts'],['dragon','cushion','held-cup']);self.assertEqual(result[0]['z_index'],5)
  self.assertEqual(result[1]['id'],'loose-cup')
 def test_overlapping_same_named_nonhuman_objects_without_identity_stay_separate(self):
  a=[self.asset('a','decoration',[10,10,60,70]),self.asset('b','panel',[12,40,65,80])]
  a[1]['parent']='a'
  self.assertEqual(planner.complete_entities(a),a)
 def test_merged_nonhuman_parts_keep_group_aliases_and_saved_plan_without_z(self):
  plan={'assets':[{'id':'dragon','name':'dragon','kind':'decoration','entity_id':'one-dragon','box':[20,10,70,65]}, {'id':'cushion','name':'cushion','kind':'panel','entity_id':'one-dragon','box':[15,55,80,82]}, {'id':'cup','name':'held cup','kind':'icon','entity_id':'one-dragon','box':[63,28,84,48]}], 'vectors':[],'texts':[], 'groups':[{'id':'entity','name':'whole dragon','children':['dragon','cushion','cup']}]}
  scene=engine.build_scene(engine.png(Image.new('RGB',(100,100),'white')),'entity',plan,lambda *_:None,lambda:False)
  entity=scene['nodes'][1]
  self.assertEqual(len(scene['nodes']),2)
  self.assertEqual(entity['sourceEntityId'],'one-dragon')
  self.assertEqual(entity['sourceEntityParts'],['dragon','cushion','cup'])
  self.assertEqual(scene['groups'][0]['children'],[entity['id']])

class NativeFontIntegration(unittest.TestCase):
 def native(self,scene):
  root=Path(__file__).resolve().parents[2]
  js="const fs=require('fs'),path=require('path'),root=process.argv[1],nm=path.join(root,'依赖/构建工具/node_modules'),cv=require(path.join(nm,'@napi-rs/canvas')),ag=require(path.join(nm,'ag-psd'));globalThis.document={createElement:()=>cv.createCanvas(1,1)};globalThis.Path2D=cv.Path2D;globalThis.ShijieNodeCanvas=cv;ag.initializeCanvas(cv.createCanvas);const S=require(path.join(root,'开发源码/自动拆图/scene-native.cjs'));(async()=>{const s=JSON.parse(fs.readFileSync(0,'utf8')),raw=Buffer.from(await S.psd(s)),p=ag.readPsd(raw),l=p.children.find(n=>n.text);process.stdout.write(JSON.stringify({signature:raw.subarray(0,4).toString(),font:l.text.style.font.name,text:l.text.text,transform:l.text.transform}));})().catch(e=>{console.error(e);process.exitCode=1});"
  r=subprocess.run(['node','-e',js,str(root)],input=json.dumps(scene),capture_output=True,text=True,encoding='utf8')
  self.assertEqual(r.returncode,0,r.stderr)
  native=json.loads(r.stdout);self.assertEqual(native['signature'],'8BPS')
  return native

 @unittest.skipUnless(os.environ.get('SHIJIE_NATIVE_TEST')=='1','actual local PSD font kernel is opt-in')
 def test_real_title_approximation_reaches_native_psd_without_distortion(self):
  source=Path('C:/Users/tuyou/AppData/Local/Temp/codex-clipboard-55a3c7dd-82ce-49c7-bfc3-8ff00f2bf2bf.png')
  if not source.is_file():self.skipTest('original user regression ROI unavailable')
  rgb=np.array(Image.open(source).convert('RGB'))
  nodes,_=engine.text_nodes([text_row('LIFE ATTITUDE',[73,74,484,152])],rgb,set())
  scene={'format':'shijie-scene','version':2,'width':794,'height':900,'nodes':nodes,'groups':[],'edges':[]}
  native=self.native(scene)
  self.assertEqual(native['font'],'Haettenschweiler')
  self.assertEqual(native['text'].strip(),'LIFE ATTITUDE')
  self.assertEqual(native['transform'][:4],[1,0,0,1])

 @unittest.skipUnless(os.environ.get('SHIJIE_NATIVE_TEST')=='1','actual local PSD font kernel is opt-in')
 def test_selected_impact_reaches_editable_psd_without_horizontal_scaling(self):
  text='LIFE ATTITUDE';font=ImageFont.truetype('C:/Windows/Fonts/impact.ttf',60)
  im=Image.new('RGB',(420,100),'white');ImageDraw.Draw(im).text((10,5),text,font=font,fill='black')
  plan={'assets':[],'vectors':[],'texts':[{'id':'title','text':text,'box':[5,0,410,95]}],'groups':[]}
  scene=engine.build_scene(engine.png(im),'native font',plan,lambda *_:None,lambda:False)
  native=self.native(scene);self.assertEqual(native['font'],'Impact')
  self.assertEqual(native['text'].strip(),text);self.assertEqual(native['transform'][:4],[1,0,0,1])

class StackFidelity(unittest.TestCase):
 def plan(self):
  return {'assets':[{'id':'dragon','name':'dragon','kind':'decoration','entity_id':'dragon','box':[10,10,70,80],'z_index':20}],
    'vectors':[{'id':'panel','name':'panel','type':'rect','x':5,'y':5,'width':80,'height':80,'fill':'#dddddd','z_index':10}, {'id':'front','name':'front','type':'rect','x':60,'y':60,'width':15,'height':15,'fill':'#ee0000','z_index':40}],
    'texts':[{'id':'copy','text':'TEXT','box':[15,15,60,35],'z_index':30}],'groups':[]}
 def build(self,plan):
  fake={'id':'native-copy','name':'TEXT','type':'text','text':'TEXT','x':15,'y':15,'width':45,'height':20,'fontSize':16,'fill':'#000000','sourceTextId':'copy'}
  with patch('engine.text_nodes',return_value=([fake],None)):
   return engine.build_scene(engine.png(Image.new('RGB',(100,100),'white')),'order',plan,lambda *_:None,lambda:False)
 def ids(self,scene):
  return [n.get('sourceAssetId') or n.get('sourceTextId') or n.get('sourceVectorId') or 'background' for n in scene['nodes']]
 def test_explicit_z_index_interleaves_assets_vectors_and_text_after_background(self):
  self.assertEqual(self.ids(self.build(self.plan())),['background','panel','dragon','copy','front'])
 def test_legacy_no_z_puts_panels_below_objects_and_text(self):
  p=self.plan()
  for rows in ('assets','vectors','texts'):
   for a in p[rows]:a.pop('z_index',None)
  self.assertEqual(self.ids(self.build(p))[-1],'copy')
  self.assertLess(self.ids(self.build(p)).index('panel'),self.ids(self.build(p)).index('dragon'))
 def test_invalid_layer_z_fails_before_generation_instead_of_being_ignored(self):
  for collection in ('assets','texts','vectors'):
   for z in (True,'front',float('nan')):
    with self.subTest(collection=collection,z=z):
     p=self.plan();p[collection][0]['z_index']=z
     with self.assertRaises(ValueError):self.build(p)
 def test_group_children_follow_actual_stack_even_if_plan_lists_them_backwards(self):
  p=self.plan();p['groups']=[{'id':'content','name':'content','children':['copy','dragon']}]
  s=self.build(p);names={n['id']:n.get('sourceAssetId') or n.get('sourceTextId') for n in s['nodes']}
  self.assertEqual([names[i] for i in s['groups'][0]['children']],['dragon','copy'])
 def test_noncontiguous_group_cannot_silently_change_front_to_back_order(self):
  p=self.plan();p['groups']=[{'id':'bad','name':'bad','children':['dragon','front']}]
  with self.assertRaisesRegex(ValueError,'交错|连续'):self.build(p)

if __name__=='__main__':unittest.main()
