import copy,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from test_assistant_split import AssistantSplitTests
from generation_stages import token
import assistant_split

class AllGenerationTests(unittest.TestCase):
 def test_explicit_single_limit_submits_one_without_remaking_completed(self):
  body=AssistantSplitTests().body()
  body['layers']=[dict(body['layers'][0],name='独立素材'+str(i),instruction='独立素材要求'+str(i)) for i in range(7)]
  body.update(stage='image',imageLimit=1)
  layer=body['layers'][0]
  kept={'id':'retained','type':'image','name':layer['name'],**layer['box'],'src':body['image'],'_generationPlanIndex':0,'_generationPlanToken':token(body)}
  body['completed']=[kept];before=copy.deepcopy(body)
  barrier=threading.Barrier(1,timeout=8);calls=[];lock=threading.Lock()
  def extract(source,node,*args):
   with lock:calls.append(node['name'])
   barrier.wait()
   return {**node,'src':body['image'],'generationRecord':{'actualImageGeneration':True,'provider':'aimake'}}
  with tempfile.TemporaryDirectory() as folder,patch('image_provider.settings',return_value={'provider':'aimake'}),patch('incremental_assets.extract_once',side_effect=extract):
   result=assistant_split.generate(body,Path(folder),lambda:False,lambda *_:None)
  self.assertEqual(len(calls),1)
  self.assertNotIn(layer['name'],calls)
  self.assertEqual(len(result['nodes']),2)
  self.assertEqual(result['nodes'][0],kept)
  self.assertEqual(body,before)
