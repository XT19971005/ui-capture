import base64,copy,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class SelectedRefineTests(unittest.TestCase):
 def setUp(self):
  self.raw=png(Image.new('RGBA',(40,40),'red'));sha=hashlib.sha256(base64.b64decode(self.raw.split(',')[1])).hexdigest()
  n={'id':'actor','name':'角色','type':'image','assetKind':'person','src':self.raw,'x':0,'y':0,'width':40,'height':40,'sourceAssetId':'a','sourceEntityParts':['a'],'generationRecord':{'actualImageGeneration':True,'sourceOriginalSHA256':sha,'generatedAssetSHA256':sha}}
  self.scene={'format':'shijie-scene','version':2,'title':'selected','source':self.raw,'width':40,'height':40,'recognition':{'sourceOriginalSHA256':sha,'reviewStatus':'NOT_REVIEWED'},'nodes':[n,{**n,'id':'other','name':'其它角色'}],'groups':[],'edges':[],'_partial':True}
 def run_selected(self,review,generated=None):
  import selected_refine
  with tempfile.TemporaryDirectory() as tmp,patch('acceptance.review_asset',side_effect=review),patch('incremental_assets.extract_once',return_value=generated) as generate,patch('subprocess.Popen',side_effect=AssertionError('selection must not export PSD')):
   result=selected_refine._process(self.raw,'selected',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,['actor'])
  return result,generate.call_count
 def test_pass_checks_only_selected_and_does_not_regenerate_or_export(self):
  checked=[]
  result,count=self.run_selected(lambda source,n,*a,**kw:checked.append(n['id']) or {'status':'PASS','issues':[]})
  self.assertEqual(checked,['actor']);self.assertEqual(count,0)
  self.assertEqual(result['nodes'][1],self.scene['nodes'][1]);self.assertTrue(result['_partial'])
  self.assertNotEqual(result['recognition']['reviewStatus'],'PASS')
 def test_bad_item_repairs_once_and_preserves_other_node_byte_for_byte(self):
  candidate={**self.scene['nodes'][0],'name':'角色','assetReviewStatus':'NOT_REVIEWED','src':png(Image.new('RGBA',(40,40),'blue'))}
  result,count=self.run_selected(lambda *a,**kw:{'status':'FAIL','issues':['颜色有误']},candidate)
  self.assertEqual(count,1);self.assertEqual(result['nodes'][0]['src'],candidate['src']);self.assertEqual(result['nodes'][1],self.scene['nodes'][1])
 def test_review_disconnect_keeps_source_and_does_not_blindly_regenerate(self):
  def fail(*a,**kw):raise RuntimeError('断线')
  result,count=self.run_selected(fail)
  self.assertEqual(count,0);self.assertEqual(result['nodes'][0]['src'],self.raw)
  self.assertIn('断线',result['nodes'][0]['reviewIssue'])
 def test_geometry_only_correction_never_regenerates_or_changes_other_layers(self):
  p={'x':5,'y':6,'width':20,'height':20,'confidence':.98,'evidence':'原图主体轮廓位于画布中央且小于当前尺寸','contentCorrect':True}
  result,count=self.run_selected(lambda *a,**kw:{'status':'FAIL','issues':['尺寸偏大'],'placement':p})
  self.assertEqual(count,0);self.assertEqual(result['nodes'][0]['src'],self.raw)
  self.assertEqual((result['nodes'][0]['x'],result['nodes'][0]['y'],result['nodes'][0]['width']),(5,6,20))
  self.assertEqual(result['nodes'][1],self.scene['nodes'][1]);self.assertTrue(result['recognition']['selectedRefine']['repairedAssetsNotRechecked'])
 def test_uncertain_geometry_preserves_pixels_and_position_without_regeneration(self):
  p={'x':5,'y':6,'width':20,'height':20,'confidence':.4,'evidence':'当前证据不能确认物体真实大小','contentCorrect':True}
  result,count=self.run_selected(lambda *a,**kw:{'status':'FAIL','issues':['尺寸不确定'],'placement':p})
  self.assertEqual(count,0);self.assertEqual(result['nodes'][0]['width'],40);self.assertEqual(result['nodes'][0]['src'],self.raw)
 def test_invalid_selection_fails_before_model(self):
  import selected_refine
  with tempfile.TemporaryDirectory() as tmp,patch('acceptance.review_asset',side_effect=AssertionError('invalid selection')):
   with self.assertRaises(ValueError):selected_refine._process(self.raw,'selected',lambda *_:None,lambda:False,self.raw,Path(tmp),self.scene,['missing'])
 def test_failed_review_cannot_retain_an_old_global_pass(self):
  self.scene['recognition'].update(reviewStatus='PASS',status='MANUAL_CONFIRMED')
  def fail(*a,**kw):raise RuntimeError('断线')
  result,count=self.run_selected(fail)
  self.assertEqual(count,0)
  self.assertEqual(result['recognition']['reviewStatus'],'NEEDS_REVIEW')
  self.assertEqual(result['recognition']['status'],'NEEDS_REVIEW')

if __name__=='__main__':unittest.main()
