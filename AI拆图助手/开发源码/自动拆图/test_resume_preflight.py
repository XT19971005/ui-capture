import base64,hashlib,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png
from incremental_assets import check_resume_assets,restore_asset

class ResumePreflightTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
  src=png(Image.new('RGBA',(4,4),'red'));raw=base64.b64decode(src.split(',')[1])
  self.node={'id':'old','name':'完整角色','type':'image','assetKind':'person','sourceAssetId':'actor','sourceEntityParts':['actor'],'x':0,'y':0,'width':4,'height':4,'src':src,'assetReviewStatus':'NOT_REVIEWED','generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':'source','generatedAssetSHA256':hashlib.sha256(raw).hexdigest()}}
  self.current={**self.node,'id':'new'};self.scene={'nodes':[self.current]};self.previous={'nodes':[self.node]}
 def check(self,review):
  with patch('acceptance.review_asset',side_effect=review):return check_resume_assets(None,self.scene,self.previous,self.folder,self.folder,'source',lambda:False,None)
 def test_checks_unreviewed_existing_bytes_before_reuse(self):
  calls=[]
  good,bad=self.check(lambda *a,**k:calls.append(a[1]['src']) or {'status':'PASS','issues':[]})
  self.assertEqual(calls,[self.node['src']]);self.assertEqual(good['actor']['src'],self.node['src']);self.assertEqual(bad,{})
 def test_bad_asset_is_targeted_but_old_pixels_retained(self):
  good,bad=self.check(lambda *a,**k:{'status':'FAIL','issues':['比例有误']})
  self.assertEqual(good,{});self.assertEqual(bad['actor']['src'],self.node['src']);self.assertIn('比例有误',bad['actor']['reviewIssue'])
 def test_disconnected_review_does_not_trigger_blind_regeneration(self):
  def fail(*a,**k):raise RuntimeError('断线')
  good,bad=self.check(fail)
  self.assertEqual(bad,{});self.assertEqual(good['actor']['src'],self.node['src']);self.assertIn('断线',good['actor']['reviewIssue'])
 def test_changed_entity_parts_are_not_reused_as_complete_character(self):
  current={**self.current,'sourceEntityParts':['actor','cushion','cup']}
  with self.assertRaisesRegex(ValueError,'实体|成员'):restore_asset(self.node,current,self.folder,self.folder,'source')
 def test_invalid_source_or_pixels_never_reuse(self):
  self.node['generationRecord']['sourceOriginalSHA256']='other'
  good,bad=self.check(lambda *a,**k:self.fail('different source must not be reviewed'))
  self.assertEqual((good,bad),({},{}))
 def test_parent_locked_asset_is_preserved_without_review(self):
  self.previous['groups']=[{'id':'g','locked':True,'children':['old']}]
  good,bad=self.check(lambda *a,**k:self.fail('parent locked image must not be reviewed'))
  self.assertEqual(good['actor']['src'],self.node['src']);self.assertEqual(bad,{})
 def test_nested_parent_locked_native_is_not_sent_to_model(self):
  from incremental_assets import check_resume_native,effective_locked_ids
  scene={'nodes':[{'id':'text','type':'text'}],'groups':[{'id':'g','locked':True,'children':['sub']},{'id':'sub','children':['text']}]}
  with patch('codex_client.CLIENT.analyze',side_effect=AssertionError('locked native must not be submitted')):
   self.assertEqual(check_resume_native(None,scene,lambda:False,None),scene)
  self.assertEqual(effective_locked_ids(scene),{'g','sub','text'})

if __name__=='__main__':unittest.main()
