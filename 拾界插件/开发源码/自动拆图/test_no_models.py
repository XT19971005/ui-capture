import base64,io,importlib.abc,subprocess,sys,unittest,json
from pathlib import Path
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
class NoLocalModelTests(unittest.TestCase):
 def test_backend_import_has_no_local_ai_framework(self):
  code="""import sys,importlib.abc
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','transformers','rapidocr','onnxruntime','segment_anything','huggingface_hub','bitsandbytes'}:raise RuntimeError('禁止本地AI:'+fullname)
sys.meta_path.insert(0,Block())
import engine,codex_pipeline,server
assert codex_pipeline.requirements()==[]
print('PASS no model imports')
"""
  p=subprocess.run([sys.executable,'-X','utf8','-B','-c',code],cwd=Path(__file__).parent,capture_output=True,text=True)
  self.assertEqual(p.returncode,0,p.stderr)
 def test_initial_scene_has_native_text_vector_and_complete_asset_proposals(self):
  from engine import build_scene
  im=Image.new('RGB',(500,220),'#ffc0a0');d=ImageDraw.Draw(im);d.rectangle((20,20,130,80),fill='red');d.rectangle((260,15,460,200),fill='#bdb4aa')
  stream=io.BytesIO();im.save(stream,format='PNG');src='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
  plan={'assets':[{'id':'logo','name':'logo','kind':'logo','box':{'left':20,'top':20,'right':131,'bottom':81},'parent':None},{'id':'person','name':'完整人物','kind':'person','box':{'left':260,'top':15,'right':461,'bottom':201},'parent':None}], 'texts':[{'id':'t1','text':'Editable text','box':{'left':20,'top':120,'right':245,'bottom':165}}], 'art_text_ids':[], 'text_corrections':[], 'vectors':[]}
  result=build_scene(src,'fixture',plan,lambda *_:None,lambda:False)
  self.assertTrue(any(n['type']=='text' and n['text']=='Editable text' for n in result['nodes']))
  self.assertTrue(any(n['type']=='path' for n in result['nodes']))
  asset=next(n for n in result['nodes'] if n.get('assetKind')=='person');self.assertEqual(asset['type'],'image');self.assertEqual(asset['provenance'],'pending-image-generation')
  self.assertFalse(result['recognition'].get('reviewStatus')=='PASS')
 def test_offline_request_is_rejected_without_launching_job(self):
  import server
  r=server.app.test_client().post('/jobs',base_url='http://127.0.0.1:19217',headers={'X-Shijie-Token':server.TOKEN},json={'mode':'smart','image':'data:image/png;base64,AA=='})
  self.assertEqual(r.status_code,400)
if __name__=='__main__':unittest.main()
