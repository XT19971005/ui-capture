import sys,tempfile,json,base64,hashlib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_transport import export_envelope

class TransportTests(unittest.TestCase):
 def test_existing_bytes_are_preserved(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'拾界'/'本轮';p.mkdir(parents=True);data=b'PK\x03\x04test';(p/'完整素材与PSD.zip').write_bytes(data)
   v=json.loads(export_envelope(root,'本轮'));self.assertEqual(base64.b64decode(v['base64']),data);self.assertEqual(v['sha256'],hashlib.sha256(data).hexdigest());self.assertFalse(v['generated_again'])
 def test_traversal_and_missing_exports_fail_without_generation(self):
  with tempfile.TemporaryDirectory() as root:
   for name in ('../other','..','x/y','x\\y','missing'):
    with self.assertRaises(ValueError):export_envelope(root,name)

if __name__=='__main__':unittest.main()
