import unittest
import planner
class CompleteEntityTests(unittest.TestCase):
 def asset(self,ident,entity,box,kind='person'):
  return {'id':ident,'name':ident,'entityId':entity,'kind':kind,'box':box,'parent':None}
 def test_same_person_body_parts_become_one_complete_generation_proposal(self):
  assets=[self.asset('whole','person-a',[10,10,40,50]),self.asset('hand','person-a',[30,20,50,35]),self.asset('other','person-b',[60,5,90,55])]
  result=planner.complete_entities(assets)
  self.assertEqual(len(result),2);self.assertEqual(result[0]['box'],[10,10,50,50]);self.assertEqual(result[0]['entityId'],'person-a');self.assertEqual(result[0]['entityParts'],['whole','hand'])
  self.assertEqual(result[1]['id'],'other')
 def test_independent_people_with_same_name_are_kept(self):
  assets=[self.asset('a','person-a',[1,1,30,50]),self.asset('b','person-b',[25,1,55,50])]
  for a in assets:a['name']='人物'
  self.assertEqual(len(planner.complete_entities(assets)),2)
 def test_parent_or_overlap_alone_does_not_invent_shared_person_identity(self):
  assets=[self.asset('a','',[1,1,30,50]),self.asset('b','',[2,1,31,50])];assets[1]['parent']='a'
  self.assertEqual(len(planner.complete_entities(assets)),2)
 def test_same_name_complete_assets_have_separate_generated_files_and_identity(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  from PIL import Image
  from runtime import ROOT
  import workflow_assets as assets
  with tempfile.TemporaryDirectory(dir=ROOT/'依赖/运行临时',prefix='entity-regression-') as folder:
   home=Path(folder);materials=home/'project/1_过程/01_素材';structure=home/'project/1_过程/02_结构';materials.mkdir(parents=True);structure.mkdir(parents=True)
   source=home/'原图.png';Image.new('RGB',(100,60),'white').save(source)
   def generate(prompt,images,target,**kwargs):
    # Deterministic stub only tests file isolation, not visual acceptance.
    Image.new('RGBA',(16,20),(100 if 'actor-a' in str(target) else 20,30,50,128)).save(target)
    return {'file':str(target),'actualImageGeneration':False}
   results=[]
   with patch.object(assets.CLIENT,'generate',side_effect=generate):
    for ident,x in [('actor-a',10),('actor-b',60)]:
     results.append(assets.complete_asset(source,{'id':ident,'name':'人物','x':x,'y':10,'width':20,'height':30,'assetKind':'person','sourceEntityId':ident},materials,structure,lambda:False))
   files=list(materials.glob('完整_*.png'));self.assertEqual(len(files),2);self.assertNotEqual(results[0]['src'],results[1]['src']);self.assertEqual([n['sourceEntityId'] for n in results],['actor-a','actor-b'])
if __name__=='__main__':unittest.main()
