import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from knowledge_store import make_bundle,load_knowledge,knowledge_prompt,verify_ack

class KnowledgeTests(unittest.TestCase):
 def test_canonical_skill_sources_are_included_in_full_without_truncation(self):
  import hashlib
  skills=Path(__file__).resolve().parents[2];workspace=skills.parent
  bundle=load_knowledge()
  expected=[skills/'game-ui-to-psd/SKILL.md',skills/'qp-image-split-expert/SKILL.md']
  for directory in [skills/'game-ui-to-psd/references',skills/'qp-image-split-expert/references']:
   expected+=sorted(p for p in directory.iterdir() if p.suffix in ('.md','.json'))
  self.assertEqual({r['path'] for r in bundle['sources']},{p.relative_to(workspace).as_posix() for p in expected})
  for r in bundle['sources']:
   source=workspace/r['path']
   self.assertEqual(r['content'],source.read_bytes().decode('utf-8-sig'))
   self.assertEqual(r['raw_sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
 def bundle(self):return make_bundle('1.1.0',[{'path':'技能包/a/SKILL.md','content':'完整规则：孔洞、同款复用，不截断。'}],{'a':'1'})
 def test_full_text_is_sent_with_verifiable_receipt(self):
  b=self.bundle();prompt=knowledge_prompt(b)
  self.assertIn(b['sources'][0]['content'],prompt)
  self.assertIn(b['sha256'],prompt)
  verify_ack({'knowledge_ack':b['receipt']},b)
 def test_tampered_or_missing_knowledge_fails_closed(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'knowledge.json'
   with self.assertRaises(ValueError):load_knowledge(p)
   b=self.bundle();b['sources'][0]['content']='被改过';p.write_text(json.dumps(b),encoding='utf-8')
   with self.assertRaises(ValueError):load_knowledge(p)
 def test_missing_or_old_model_ack_is_rejected(self):
  b=self.bundle()
  for reply in [{},{'knowledge_ack':dict(b['receipt'],sha256='old')}]:
   with self.assertRaises(ValueError):verify_ack(reply,b)
 def test_version_changes_when_source_changes(self):
  a=self.bundle();sources=copy.deepcopy(a['sources']);sources[0]['content']+='新增规则'
  b=make_bundle('1.1.0',sources,{'a':'1'})
  self.assertNotEqual(a['sha256'],b['sha256'])
