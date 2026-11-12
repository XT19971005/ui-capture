import json,sys,tempfile,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stage_resume import StageStore
from knowledge_store import load_knowledge

class ResumeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.rgb=np.zeros((20,30,3),np.uint8);self.k=load_knowledge()
  self.inv=json.dumps(dict(width=30,height=20,knowledge_ack=self.k['receipt'],background_prompt='Blue background',items=[dict(id='label',name='文字',bucket='texts',parent_id=None)]))
  self.store=StageStore(self.tmp.name,self.rgb,self.k)
 def test_empty_branch_never_needs_model(self):
  value,reason=self.store.lookup('vectors',self.inv)
  self.assertEqual(json.loads(value)['assets'],[]);self.assertEqual(reason,'SKIPPED_EMPTY')
 def test_valid_reply_survives_new_instance(self):
  reply=json.dumps({'assets':[dict(id='label',method='text',box=[0,0,20,10],text='Hi',color=[0,0,0])]})
  self.store.save('texts',self.inv,reply)
  value,reason=StageStore(self.tmp.name,self.rgb,self.k).lookup('texts',self.inv)
  self.assertEqual(value,reply);self.assertEqual(reason,'CACHED_VALIDATED')
 def test_foreign_or_missing_ids_not_saved(self):
  for rows in ([],[dict(id='other',method='text')]):
   with self.assertRaises(ValueError):self.store.save('texts',self.inv,json.dumps(dict(assets=rows)))
  self.assertEqual(self.store.lookup('texts',self.inv),(None,'NEEDS_AGENT'))
 def test_changed_source_or_inventory_does_not_reuse(self):
  self.store.save('inventory','',self.inv)
  changed=self.rgb.copy();changed[0,0,0]=1
  self.assertIsNone(StageStore(self.tmp.name,changed,self.k).lookup('inventory','')[0])
 def test_tampered_cache_rejected(self):
  self.store.save('inventory','',self.inv)
  p=next(Path(self.tmp.name).glob('*.json'));v=json.loads(p.read_text());v['reply']='{}';p.write_text(json.dumps(v))
  with self.assertRaisesRegex(ValueError,'摘要'):self.store.lookup('inventory','')
 def test_request_omits_other_branches_full_context(self):
  from staged_expert import branch_request
  s=branch_request(self.rgb,self.k,'texts',self.inv)
  self.assertNotIn('父子分类上下文=',s)

if __name__=='__main__':unittest.main()
