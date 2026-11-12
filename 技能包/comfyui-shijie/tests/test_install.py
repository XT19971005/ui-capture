from pathlib import Path
import sys,unittest,tempfile,io,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from install import prepare_support
class InstallerTests(unittest.TestCase):
 def test_server_hook_never_downloads_weights_and_checks_support_hash(self):
  data=b'{"model_type":"qwen3_vl"}';sha=hashlib.sha256(data).hexdigest();calls=[]
  files=[{'name':'model.safetensors','url':'forbidden','size_bytes':4255140312,'sha256':'unused'},{'name':'config.json','url':'https://modelscope.cn/models/Qwen/Qwen3-VL-2B-Instruct/resolve/master/config.json','size_bytes':len(data),'sha256':sha}]
  def fetch(url,**kw):calls.append(url);return io.BytesIO(data)
  with tempfile.TemporaryDirectory() as temp:
   self.assertEqual(prepare_support(temp,fetch,{'files':files}),1);self.assertEqual(len(calls),1)
   self.assertEqual((Path(temp)/'config.json').read_bytes(),data)
   self.assertEqual(prepare_support(temp,fetch,{'files':files}),1);self.assertEqual(len(calls),1)
 def test_bad_support_checksum_does_not_activate_file(self):
  f={'name':'config.json','url':'https://modelscope.cn/models/Qwen/Qwen3-VL-2B-Instruct/resolve/master/config.json','size_bytes':3,'sha256':'0'*64}
  with tempfile.TemporaryDirectory() as temp:
   with self.assertRaises(ValueError):prepare_support(temp,lambda *a,**k:io.BytesIO(b'bad'),{'files':[f]})
   self.assertEqual(list(Path(temp).iterdir()),[])
 def test_model_list_merge_preserves_other_nodes(self):
  from prepare_server_models import merge_dependencies
  old=[{'node_id':'14','input':'unet_name','filename':'qwen.safetensors'},{'node_id':'104','input':'model_file_0','filename':'old.safetensors'}]
  new=[{'node_id':'104','input':'model_file_0','filename':'new.safetensors'}]
  merged=merge_dependencies(old,new)
  self.assertEqual(len(merged),2);self.assertEqual(merged[0]['filename'],'qwen.safetensors');self.assertEqual(merged[1]['filename'],'new.safetensors')
if __name__=='__main__':unittest.main()
