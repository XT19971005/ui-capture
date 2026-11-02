import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import engine, codex_pipeline, incremental_assets

class FirstPassTests(unittest.TestCase):
 def test_first_pass_returns_layers_without_review_or_psd_export(self):
  raw=engine.png(Image.new('RGB',(24,24),'gray'))
  plan={'project_name':'测试','assets':[],'texts':[],'art_text_ids':[],'text_corrections':[],'groups':[],'warnings':[],'vectors':[]}
  nodes=[{'id':i,'name':i,'type':'image','x':0,'y':0,'width':24,'height':24,'src':raw,'assetKind':'background' if i=='bg' else 'icon'} for i in ['bg','asset']]
  scene={'format':'shijie-scene','version':2,'title':'测试','source':raw,'width':24,'height':24,'nodes':nodes,'recognition':{'warnings':[]},'edges':[]}
  def generate(source,n,*a,**kw):return {**n,'provenance':'codex-image-generation'}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_pipeline.CLIENT.model',return_value='test-model'),patch('codex_pipeline.CLIENT.analyze',return_value=plan) as analysis,patch('engine.build_scene',return_value=scene),patch('workflow_assets.complete_background'),patch('workflow_assets.complete_asset',side_effect=generate) as generated,patch('acceptance.review_asset',side_effect=AssertionError('first pass may not visually review')),patch('subprocess.Popen',side_effect=AssertionError('first pass may not export PSD')):
   result=codex_pipeline._process(raw,'测试',lambda *_:None,lambda:False,raw,Path(tmp))
  self.assertEqual(generated.call_count,1)
  self.assertEqual(analysis.call_count,1,'only planning, no final image review')
  self.assertEqual(len(result['nodes']),2)
  self.assertEqual(result['recognition']['reviewStatus'],'NOT_REVIEWED')
  self.assertNotIn('delivery',result)
 def test_extract_once_does_not_retry_or_review(self):
  candidate={'id':'a','name':'原图素材','type':'image'}
  with patch('workflow_assets.complete_asset',return_value=dict(candidate)) as generated,patch('acceptance.review_asset',side_effect=AssertionError('must not review')):
   result=incremental_assets.extract_once(None,candidate,None,None,lambda:False,None,None)
  self.assertEqual(generated.call_count,1)
  self.assertEqual(result['assetReviewStatus'],'NOT_REVIEWED')
 def test_extract_once_cancel_never_becomes_fallback(self):
  with patch('workflow_assets.complete_asset',side_effect=InterruptedError('已取消')):
   with self.assertRaises(InterruptedError):incremental_assets.extract_once(None,{'name':'物件'},None,None,lambda:False,None,None)

if __name__=='__main__':unittest.main()
