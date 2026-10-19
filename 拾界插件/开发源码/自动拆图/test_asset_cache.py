import hashlib,json,tempfile,unittest
from pathlib import Path
from PIL import Image
import workflow_assets as W
from runtime import ROOT

class AssetCacheTests(unittest.TestCase):
 def test_reuse_requires_same_original_bytes_and_actual_generated_asset(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'依赖/运行临时') as folder:
   home=Path(folder);old=home/'previous';qa=old/'1_过程/02_结构';assets=old/'1_过程/01_素材';output=old/'2_输出'
   for p in (qa,assets,output):p.mkdir(parents=True)
   (output/'旧_原图.jpg').write_bytes(b'original');Image.new('RGB',(20,10),'blue').save(assets/'完整干净背景.png')
   (qa/'背景补全来源.json').write_text(json.dumps({'actualImageGeneration':True}),'utf8')
   digest=hashlib.sha256(b'original').hexdigest()
   self.assertIsNotNone(W.reusable_background(home,digest))
   self.assertIsNone(W.reusable_background(home,hashlib.sha256(b'other').hexdigest()))
   (qa/'背景补全来源.json').write_text(json.dumps({'actualImageGeneration':False}),'utf8')
   self.assertIsNone(W.reusable_background(home,digest))
 def test_complex_asset_reuse_requires_actual_generation_and_individual_visual_pass(self):
  with tempfile.TemporaryDirectory(dir=ROOT/'依赖/运行临时') as folder:
   home=Path(folder);project=home/'old';structure=project/'1_过程/02_结构';qa=project/'1_过程/03_检查';assets=project/'1_过程/01_素材';out=project/'2_输出'
   for p in (structure,qa,assets,out):p.mkdir(parents=True)
   (out/'旧_原图.jpg').write_bytes(b'original');file=assets/'full.png';Image.new('RGBA',(100,100),(100,30,20,255)).save(file)
   node=W.image_node(file,'Subject',[10,10,100,100]);node.update(id='subject',assetKind='person')
   (structure/'工程.scene.json').write_text(json.dumps({'nodes':[node]}),'utf8');(structure/'补全_subject.json').write_text(json.dumps({'actualImageGeneration':True,'transparent':True,'file':str(file)}),'utf8')
   review=qa/'Codex画面复核.json';review.write_text(json.dumps({'asset_checks':[{'name':'Subject','status':'FAIL'}]}),'utf8')
   proposed={'name':'Subject','assetKind':'person','x':15,'y':15,'width':90,'height':90};digest=hashlib.sha256(b'original').hexdigest()
   self.assertIsNone(W.reusable_complete_asset(home,digest,proposed))
   review.write_text(json.dumps({'asset_checks':[{'name':'Subject','status':'PASS'}]}),'utf8')
   self.assertIsNone(W.reusable_complete_asset(home,digest,proposed))
   psd=out/'verified.psd';psd.write_bytes(b'verified psd');(structure/'工程.scene.json').write_text(json.dumps({'nodes':[node],'delivery':{'psd':str(psd)}}),'utf8')
   independent=qa/'独立图层';independent.mkdir();layer=independent/'001_Subject.png';layer.write_bytes(file.read_bytes())
   (qa/'独立回读图层来源.json').write_text(json.dumps({'psdSHA256':hashlib.sha256(psd.read_bytes()).hexdigest(),'layers':[{'name':'Subject','file':'独立图层/001_Subject.png','sha256':hashlib.sha256(layer.read_bytes()).hexdigest(),'nativeComposite':True}]}),'utf8')
   self.assertIsNotNone(W.reusable_complete_asset(home,digest,proposed));self.assertIsNone(W.reusable_complete_asset(home,hashlib.sha256(b'other').hexdigest(),proposed))

if __name__=='__main__':unittest.main()
