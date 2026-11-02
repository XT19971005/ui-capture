import copy,tempfile,unittest
from pathlib import Path
from PIL import Image
from runtime import TEMP
from layer_review import review_errors

class ColorFidelityTests(unittest.TestCase):
 def fixture(self):
  scene={'nodes':[{'name':'人物','type':'image','assetKind':'person'}],'recognition':{'colorFidelityRequired':True}}
  check={'name':'人物','status':'PASS','notes':'完整人体，但尚无颜色比较','file':'03_检查/独立图层/001_人物.png'}
  review={'status':'PASS','asset_checks':[copy.deepcopy(check)],'file_checks':[copy.deepcopy(check)]}
  return scene,review,{'checks':[copy.deepcopy(check)]}
 def test_whole_layer_pass_cannot_skip_color_observation(self):
  scene,review,checks=self.fixture();self.assertTrue(review_errors(scene,review,checks))
 def test_color_failure_blocks_even_when_structure_passes(self):
  scene,review,checks=self.fixture();review['color_checks']=[{'name':'人物','status':'FAIL','notes':'肤色和外套饱和度明显改变'}];self.assertTrue(review_errors(scene,review,checks))
 def test_each_layer_requires_unique_actual_color_observation(self):
  scene,review,checks=self.fixture();review['color_checks']=[{'name':'人物','status':'PASS','notes':'肤色、外套、头发逐处对照原图，未见明显偏色'}];self.assertFalse(review_errors(scene,review,checks))
  for values in ([review['color_checks'][0],review['color_checks'][0]],[{'name':'人物','status':'PASS','notes':' '}],[{'name':'未知','status':'PASS','notes':'颜色相同'}]):
   changed=copy.deepcopy(review);changed['color_checks']=values;self.assertTrue(review_errors(scene,changed,checks))
 def test_legacy_review_records_remain_valid_without_new_flag(self):
  scene,review,checks=self.fixture();scene['recognition']={};self.assertFalse(review_errors(scene,review,checks))
 def test_color_failed_asset_cannot_be_reused_as_approved(self):
  from layer_review import approved_asset_names
  scene,review,_=self.fixture();review['color_checks']=[{'name':'人物','status':'FAIL','notes':'偏色'}]
  self.assertEqual(approved_asset_names(scene,review),set())
  review['color_checks'][0].update(status='PASS',notes='颜色逐处一致')
  self.assertEqual(approved_asset_names(scene,review),{'人物'})
 def test_explicit_color_failure_is_not_ignored_by_legacy_flag(self):
  from layer_review import approved_asset_names
  scene,review,_=self.fixture();scene['recognition']={};review['color_checks']=[{'name':'人物','status':'FAIL','notes':'已有明确偏色记录'}]
  self.assertEqual(approved_asset_names(scene,review),set())
 def test_failed_entity_cache_is_evicted_before_replanning_can_rename_it(self):
  from layer_review import discard_failed_assets
  key=('same-person','person',10,10,100,200);cache={key:{'name':'原人物名','src':'bad-color'},'good':{'name':'已好人物','src':'keep'}}
  discard_failed_assets(cache,{'原人物名'})
  self.assertNotIn(key,cache);self.assertEqual(cache['good']['src'],'keep')
 def test_all_non_atlas_check_images_are_actually_attached(self):
  from workflow_assets import review_reference_files
  with tempfile.TemporaryDirectory(dir=TEMP) as folder:
   qa=Path(folder)/'03_检查';qa.mkdir();names=['并排.png','浅色.png','深色.png','棋盘.png']
   for name in names:Image.new('RGB',(5,5),'gray').save(qa/name)
   checks={'checks':[{'name':n,'file':'03_检查/'+n} for n in names]+[{'name':'人物','file':'03_检查/独立图层/001_人物.png'}]}
   self.assertEqual([p.name for p in review_reference_files(qa,checks)],names)
   (qa/'棋盘.png').unlink()
   with self.assertRaises(ValueError):review_reference_files(qa,checks)
 def test_review_reference_cannot_read_outside_check_directory(self):
  from workflow_assets import review_reference_files
  with tempfile.TemporaryDirectory(dir=TEMP) as folder:
   qa=Path(folder)/'03_检查';qa.mkdir()
   with self.assertRaises(ValueError):review_reference_files(qa,{'checks':[{'name':'bad','file':'../../outside.png'}]})

if __name__=='__main__':unittest.main()
