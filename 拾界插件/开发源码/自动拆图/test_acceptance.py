import base64,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import acceptance
import workflow_assets
from layer_review import review_errors

class AcceptanceTests(unittest.TestCase):
 def test_uncertain_geometry_is_not_converted_to_pixel_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);src=folder/'source.png';Image.new('RGB',(30,30),'gray').save(src)
   node={'id':'fan','name':'扇子','x':0,'y':0,'width':30,'height':30,'src':'data:image/png;base64,'+base64.b64encode(src.read_bytes()).decode()}
   checks=[{'name':n,'status':'PASS','notes':'已观察，边界部分不明确'} for n in acceptance.ASSET_CRITERIA]
   with patch('acceptance.CLIENT.analyze',return_value={'status':'NEEDS_REVIEW','checks':checks,'issues':['尺寸证据不足'],'placement':None}):
    result=acceptance.review_asset(src,node,folder,lambda:False)
   self.assertEqual(result['status'],'NEEDS_REVIEW')
 def test_failed_asset_message_is_short_and_keeps_real_observations(self):
  checks=[{'name':n,'status':'PASS','notes':'对照观察'} for n in acceptance.ASSET_CRITERIA]
  checks[2]['status']='FAIL';checks[3]['status']='FAIL'
  result={'status':'FAIL','checks':checks,'issues':['偏色和孔洞残影的完整实际观察'*30]}
  error=acceptance.AssetReviewError('外框',result)
  self.assertLess(len(str(error)),70);self.assertIn('颜色',str(error));self.assertIn('透明边缘',str(error))
  self.assertEqual(error.diagnostics['checks'],checks);self.assertEqual(error.diagnostics['issues'],result['issues'])
 def test_missing_or_duplicate_categories_never_pass(self):
  checks=[{'name':n,'status':'PASS','notes':'实际对照观察'} for n in acceptance.FINAL_CRITERIA]
  scene={'nodes':[{'name':'图层'}],'recognition':{'acceptanceRequired':True}}
  review={'status':'PASS','asset_checks':[{'name':'图层','status':'PASS','notes':'看过实际图层'}],'file_checks':[{'name':'实图','status':'PASS','notes':'看过实际文件'}],'acceptance_checks':checks}
  checklist={'checks':review['file_checks']}
  self.assertEqual(review_errors(scene,review,checklist),[])
  review['acceptance_checks']=checks[:-1];self.assertTrue(review_errors(scene,review,checklist))
  review['acceptance_checks']=checks+[checks[0]];self.assertTrue(review_errors(scene,review,checklist))
 def test_asset_rejects_color_fail_and_cleans_images(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);src=folder/'source.png';Image.new('RGB',(30,30),'gray').save(src)
   png=folder/'generated.png';Image.new('RGBA',(20,20),'orange').save(png)
   node={'id':'asset','name':'物品','x':5,'y':5,'width':20,'height':20,'src':'data:image/png;base64,'+base64.b64encode(png.read_bytes()).decode()}
   checks=[{'name':n,'status':'PASS','notes':'原图与独立素材已对照'} for n in acceptance.ASSET_CRITERIA]
   checks[2].update(status='FAIL',notes='橙色明显过饱和')
   with patch('acceptance.CLIENT.analyze',return_value={'status':'PASS','checks':checks,'issues':[]}):
    result=acceptance.review_asset(src,node,folder,lambda:False)
   self.assertEqual(result['status'],'FAIL');self.assertTrue(any('颜色' in i for i in result['issues']))
   self.assertEqual(sorted(p.name for p in folder.iterdir()),['generated.png','source.png','逐件复核_asset.json'])
 def test_planner_keeps_more_than_forty_independent_objects(self):
  from planner import parse_plan
  rows=[{'id':str(i),'name':'独立图片'+str(i),'kind':'icon','box':[i*10,0,i*10+9,10]} for i in range(48)]
  result=parse_plan(json.dumps({'assets':rows}),600,100,input_size=(600,100))
  self.assertEqual(len(result['assets']),48)
 def test_retry_reuse_keeps_source_record_for_current_uuid(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);png=folder/'complete.png';Image.new('RGBA',(4,4),'red').save(png)
   record={'file':str(png),'actualImageGeneration':True,'transparent':True}
   (folder/'补全_old.json').write_text(json.dumps(record),'utf8')
   prior={'id':'old','name':'旧','src':'data:image/png;base64,'+base64.b64encode(png.read_bytes()).decode()}
   current={'id':'new','name':'当前'}
   workflow_assets.reuse_current_asset(prior,current,folder)
   self.assertEqual(json.loads((folder/'补全_new.json').read_text('utf8'))['reusedCurrentAttemptFromId'],'old')
 def test_pipeline_invokes_real_asset_review_before_publishing(self):
  import inspect,codex_pipeline
  import incremental_assets
  source=inspect.getsource(incremental_assets.extract_checked)
  self.assertIn('quality=review_asset(',source)
  self.assertLess(source.index('quality=review_asset('),source.index("assetReviewStatus='PASS'"))
  self.assertIn("assetReviewStatus='NEEDS_REVIEW'",source)
  self.assertEqual(codex_pipeline.PLAN['properties']['assets']['maxItems'],120)
  self.assertIn('acceptance_checks',codex_pipeline.REVIEW['required'])
 def test_connected_vertical_chinese_is_one_editable_text(self):
  import engine,numpy as np
  canvas=Image.new('RGB',(80,160),'white')
  from PIL import ImageDraw,ImageFont
  draw=ImageDraw.Draw(canvas);font=ImageFont.truetype(str(engine.FONT),24)
  for i,ch in enumerate('河南文化'):draw.text((20,8+i*35),ch,font=font,fill='black')
  row={'id':'vertical','text':'河南文化','bbox':[20,8,48,150],'quad':[[20,8],[48,8],[48,150],[20,150]],'confidence':1}
  with patch('text_style.estimate',return_value=None):nodes,_=engine.text_nodes([row],np.array(canvas),set())
  self.assertEqual(len(nodes),1)
  self.assertEqual(nodes[0]['text'],'河\n南\n文\n化');self.assertEqual(nodes[0]['sourceTextId'],'vertical')
  self.assertAlmostEqual(nodes[0]['lineHeight'],35.5)

if __name__=='__main__':unittest.main()
