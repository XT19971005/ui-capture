import json, unittest, tempfile
from pathlib import Path
from PIL import Image
from planner import parse_plan

class EntityInstanceTests(unittest.TestCase):
 def test_copy_qualified_master_preserves_each_instance_geometry_and_order(self):
  from workflow_assets import reuse_entity_instance
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'master.png';Image.new('RGBA',(100,100),(220,30,30,255)).save(path)
   import base64
   cached={'id':'master','name':'公鸡','src':'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode(),'assetReviewStatus':'PASS','generationRecord':{'actualImageGeneration':True},'reuseEntityId':'rooster'}
   current={'id':'instance','name':'小图','type':'image','x':120,'y':130,'width':20,'height':20,'z_index':42,'sourceAssetId':'thumb','sourceEntityParts':['thumb'],'reuseEntityId':'rooster'}
   result=reuse_entity_instance(cached,current)
   self.assertEqual(result['src'],cached['src']);self.assertEqual(result['id'],'instance')
   self.assertEqual([result[k] for k in ('x','y','width','height','z_index')],[120,130,20,20,42])
   self.assertEqual(result['sourceEntityParts'],['thumb']);self.assertEqual(result['generationRecord']['reusedCurrentAttemptFromId'],'master')
   with self.assertRaises(ValueError):reuse_entity_instance({**cached,'assetReviewStatus':'NEEDS_REVIEW'},current)
 def test_same_asset_identity_in_separate_groups_keeps_two_placements(self):
  assets=[{'id':'portrait','name':'公鸡','kind':'person','entity_id':'rooster','box':[20,20,100,100]}, {'id':'thumb','name':'公鸡小图','kind':'icon','entity_id':'rooster','box':[120,120,140,140]}]
  plan={'assets':assets,'groups':[{'id':'profile','children':['portrait']},{'id':'selector','children':['thumb']}]}
  result=parse_plan(json.dumps(plan),200,200,(200,200))['assets']
  self.assertEqual(len(result),2)
  self.assertEqual([a['box'] for a in result],[[20,20,100,100],[120,120,140,140]])
  self.assertEqual([a['entityParts'] for a in result],[['portrait'],['thumb']])
  self.assertEqual([a.get('reuseEntityId') for a in result],['rooster','rooster'])
 def test_same_group_parts_still_merge(self):
  plan={'assets':[{'id':i,'name':i,'kind':'person','entity_id':'actor','box':b} for i,b in [('body',[20,20,100,100]),('hand',[100,30,120,50])]],'groups':[{'id':'actor-group','children':['body','hand']}]}
  result=parse_plan(json.dumps(plan),200,200,(200,200))['assets']
  self.assertEqual(len(result),1);self.assertEqual(result[0]['entityParts'],['body','hand'])

if __name__=='__main__':unittest.main()
