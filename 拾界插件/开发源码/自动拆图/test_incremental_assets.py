import base64,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import workflow_assets

class IncrementalTests(unittest.TestCase):
 def test_real_pipeline_reaches_next_asset_without_forced_export_after_item_failure(self):
  import engine,codex_pipeline
  raw=engine.png(Image.new('RGB',(100,100),'gray'))
  plan={'project_name':'测试','assets':[],'texts':[],'art_text_ids':[],'text_corrections':[],'groups':[],'warnings':[],'vectors':[]}
  nodes=[{'id':'bg','name':'背景','type':'image','x':0,'y':0,'width':100,'height':100,'src':raw},*({'id':i,'name':i,'type':'image','assetKind':'icon','sourceAssetId':i,'x':0,'y':0,'width':20,'height':20,'src':raw} for i in ['bad','good'])]
  scene={'format':'shijie-scene','version':2,'title':'测试','width':100,'height':100,'nodes':nodes,'recognition':{'warnings':[]},'edges':[]}
  class ExportReached(BaseException):pass
  observed=[]
  def checked(source,candidate,*args,**kwargs):
   observed.append(candidate['name']);return {**candidate,'assetReviewStatus':'NEEDS_REVIEW' if candidate['id']=='bad' else 'PASS','reviewIssue':'偏色' if candidate['id']=='bad' else ''}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.analyze',return_value=plan),patch('engine.build_scene',return_value=scene),patch('workflow_assets.complete_background'),patch('incremental_assets.extract_once',side_effect=checked),patch('codex_pipeline.CLIENT.model',return_value='test-model'),patch('subprocess.Popen',side_effect=ExportReached),patch('shutil.which',return_value='node'):
   result=codex_pipeline._process(raw,'测试',lambda *_:None,lambda:False,raw,Path(tmp))
   self.assertNotIn('delivery',result)
   self.assertEqual(len(result['nodes']),3)
  self.assertEqual(observed,['bad','good'])
 def test_bad_asset_kept_with_warning_and_next_asset_can_finish(self):
  from incremental_assets import extract_checked
  node={'id':'a','name':'外框','type':'image'}
  candidate={**node,'src':'data:image/png;base64,AA=='}
  review={'status':'FAIL','issues':['偏色'],'checks':[]}
  with patch('workflow_assets.complete_asset',return_value=candidate),patch('acceptance.review_asset',return_value=review):
   result=extract_checked(Path('source'),node,None,None,lambda:False,None,None)
  self.assertEqual(result['assetReviewStatus'],'NEEDS_REVIEW');self.assertIn('偏色',result['reviewIssue'])
  with patch('workflow_assets.complete_asset',return_value={**candidate,'id':'b'}),patch('acceptance.review_asset',return_value={'status':'PASS','issues':[],'checks':[]}):
   self.assertEqual(extract_checked(Path('source'),{**node,'id':'b'},None,None,lambda:False,None,None)['assetReviewStatus'],'PASS')
 def test_final_review_disconnect_returns_reviewable_result(self):
  from incremental_assets import review_or_pending
  result=review_or_pending(lambda:(_ for _ in ()).throw(RuntimeError('连接中断')))
  self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertIn('连接中断',result['summary'])
  with self.assertRaises(InterruptedError):review_or_pending(lambda:(_ for _ in ()).throw(InterruptedError('取消')))
 def test_cancel_is_never_downgraded_to_warning(self):
  from incremental_assets import extract_checked
  with patch('workflow_assets.complete_asset',side_effect=InterruptedError('取消')):
   with self.assertRaises(InterruptedError):extract_checked(None,{'name':'物件'},None,None,lambda:True,None,None)
 def test_resume_material_hash_and_source_validation(self):
  from incremental_assets import restore_asset
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);png=folder/'source.png';Image.new('RGBA',(4,4),'red').save(png);raw=png.read_bytes()
   node={'id':'old','name':'图','src':'data:image/png;base64,'+base64.b64encode(raw).decode(),'assetReviewStatus':'PASS','generationRecord':{'actualImageGeneration':True,'transparent':True,'sourceOriginalSHA256':'source','generatedAssetSHA256':hashlib.sha256(raw).hexdigest()}}
   restored=restore_asset(node,{**node,'id':'new'},folder,folder,'source')
   self.assertEqual(restored['src'],node['src']);self.assertEqual(restored['id'],'new')
   node['layerStyle']={'outerGlow':{'opacity':.95,'size':70}}
   edited=restore_asset(node,{**node,'layerStyle':{'outerGlow':{'opacity':.3,'size':12}}},folder,folder,'source')
   self.assertEqual(edited['layerStyle'],node['layerStyle'])
   self.assertTrue((folder/'补全_new.json').is_file())
   with self.assertRaises(ValueError):restore_asset(node,node,folder,folder,'other')
 def test_generated_glow_is_restrained_without_changing_fill(self):
  from incremental_assets import gentle_glow
  node={'fill':'#765432','layerStyle':{'outerGlow':{'opacity':.9,'size':80},'innerGlow':{'opacity':.7,'size':60}}}
  gentle_glow(node)
  self.assertEqual(node['fill'],'#765432');self.assertEqual(node['layerStyle']['outerGlow']['opacity'],.3)
  self.assertEqual(node['layerStyle']['outerGlow']['size'],12);self.assertEqual(node['layerStyle']['innerGlow']['opacity'],.2)
 def test_resume_keeps_native_text_edits_and_new_group_members(self):
  from incremental_assets import preserve_native
  old={'nodes':[{'id':'old','type':'text','sourceTextId':'t','text':'手改内容','x':37,'fill':'#123456'}],'groups':[{'id':'g','children':['old'],'layerStyle':{'outerGlow':{'opacity':.8}}}]}
  current={'nodes':[{'id':'new','type':'text','sourceTextId':'t','text':'原内容','x':0}],'groups':[{'id':'g','children':['new']}]}
  preserve_native(current,old)
  self.assertEqual(current['nodes'][0]['text'],'手改内容');self.assertEqual(current['nodes'][0]['x'],37)
  self.assertEqual(current['nodes'][0]['id'],'new');self.assertEqual(current['groups'][0]['children'],['new'])
  self.assertEqual(current['groups'][0]['layerStyle'],old['groups'][0]['layerStyle'])
 def test_resume_keeps_different_art_ink_channels_separate(self):
  from incremental_assets import preserve_native
  rows=[{'type':'path','sourceAssetId':'art','name':'艺术字#'+color,'fill':'#'+color,'id':str(i)} for i,color in enumerate(['2244cc','cc1122'])]
  old={'nodes':rows};current={'nodes':[{**n,'id':'new'+n['id']} for n in rows]}
  preserve_native(current,old)
  self.assertEqual([n['fill'] for n in current['nodes']],['#2244cc','#cc1122'])
 def test_resume_matches_planned_vector_by_source_id(self):
  from incremental_assets import preserve_native
  old={'nodes':[{'id':'old','type':'rect','sourceVectorId':'v','fill':'#abcdef'}]}
  current={'nodes':[{'id':'new','type':'rect','sourceVectorId':'v','fill':'#123456'}]}
  preserve_native(current,old);self.assertEqual(current['nodes'][0]['fill'],'#abcdef')

if __name__=='__main__':unittest.main()
