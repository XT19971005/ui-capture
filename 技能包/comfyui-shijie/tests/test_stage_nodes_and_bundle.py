import ast,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from output_bundle import bundle_outputs

class GatewayTests(unittest.TestCase):
 def test_lazy_gateway_does_not_request_reply_on_empty_or_cached_stage(self):
  tree=ast.parse((Path(__file__).resolve().parents[1]/'nodes.py').read_text('utf-8'))
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='QPStageResult')
  scope={};exec(compile(ast.Module(body=[cls],type_ignores=[]),'gateway','exec'),scope)
  node=scope['QPStageResult']()
  class Store:
   value='{"assets":[]}'
   def lookup(self,*a):return self.value,'status'
  store=Store();node.store=lambda _:store
  self.assertEqual(node.check_lazy_status(None,'vectors','inventory'),[])
  store.value=None
  self.assertEqual(node.check_lazy_status(None,'vectors','inventory'),['reply'])
  self.assertTrue(node.INPUT_TYPES()['optional']['reply'][1]['lazy'])
 def test_bundle_contains_only_actual_outputs_and_manifest(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'图.png').write_bytes(b'png');(p/'项目.psd').write_bytes(b'8BPS');(p/'无关.txt').write_text('private')
   z,m=bundle_outputs(p,p/'项目.psd')
   with zipfile.ZipFile(z) as archive:self.assertEqual(set(archive.namelist()),{'图.png','项目.psd','交付文件清单.json'})
   self.assertEqual(json.loads(m.read_text('utf-8'))['visual_status'],'NOT_REVIEWED')

if __name__=='__main__':unittest.main()
