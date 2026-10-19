import copy,importlib.util,json,unittest
from unittest.mock import patch

IMAGE='data:image/png;base64,'+'QUJD'*4096
def node(ident,src=IMAGE):return {'id':ident,'name':ident,'type':'image','x':0,'y':0,'width':10,'height':10,'src':src}
def scene():return {'format':'shijie-scene','version':2,'width':10,'height':10,'source':IMAGE,'originalSource':IMAGE,'comparisonSource':IMAGE,'nodes':[node(str(i)) for i in range(57)],'groups':[],'recognition':{'resumePendingNodes':[node('pending')],'resumeNodeOrder':[],'resumeGroups':[]}}

class ImageWireTests(unittest.TestCase):
 def module(self):
  self.assertIsNotNone(importlib.util.find_spec('image_wire'),'bounded image table transport must exist')
  import image_wire
  return image_wire
 def wire(self,job=None,images=None):return {'wireFormat':'shijie-image-table','wireVersion':1,'images':[IMAGE] if images is None else images,'job':job or {'image':{'$image':0},'original':{'$image':0},'mode':'codex'}}
 def test_decode_restores_exact_shared_strings_without_touching_text_or_modes(self):
  wire=self.wire({'image':{'$image':0},'original':{'$image':0},'mode':'refine-selected','selectedIds':['字层'],'resume':{'source':{'$image':0},'nodes':[{'src':{'$image':0},'text':IMAGE,'name':'中文😀'}]}})
  before=copy.deepcopy(wire);result=self.module().decode_job(wire)
  self.assertEqual(result['image'],IMAGE);self.assertIs(result['image'],result['resume']['nodes'][0]['src'])
  self.assertEqual(result['resume']['nodes'][0]['text'],IMAGE);self.assertEqual(result['selectedIds'],['字层']);self.assertEqual(wire,before)
 def test_large_repeated_57_layer_scene_is_measured_by_unique_bytes(self):
  module=self.module();doc=scene()
  with patch.object(module,'MAX_UNIQUE_IMAGE_BYTES',len(IMAGE)+1),patch.object(module,'MAX_METADATA_BYTES',100000),patch.object(module,'MAX_LOGICAL_IMAGE_BYTES',len(IMAGE)*100):
   usage=module.measure(doc)
  self.assertEqual(usage['uniqueImageBytes'],len(IMAGE));self.assertGreater(usage['logicalImageBytes'],len(IMAGE)*57)
 def test_unknown_missing_negative_boolean_and_extra_reference_fields_are_rejected(self):
  for value in ({'$image':1},{'$image':-1},{'$image':True},{'$image':'0'},{'$image':0,'extra':1}):
   with self.subTest(ref=value),self.assertRaises(ValueError):self.module().decode_job(self.wire({'image':value}))
  with self.assertRaises(ValueError):self.module().decode_job(self.wire({'image':{'$image':0}},[]))
 def test_references_in_text_or_arbitrary_objects_are_not_executed(self):
  for job in ({'image':{'$image':0},'title':{'$image':0}},{'image':{'$image':0},'resume':{'nodes':[{'text':{'$image':0}}]}},{'image':{'$image':0},'command':{'$image':0}}):
   with self.assertRaises(ValueError):self.module().decode_job(self.wire(job))
 def test_unsupported_wrapper_versions_unused_images_and_non_image_tables_are_rejected(self):
  for wire in ({**self.wire(),'wireVersion':2},{**self.wire(),'unknown':1},self.wire(images=[IMAGE,IMAGE]),self.wire(images=['https://example.test/private.png']),self.wire(images=[{'$image':0}])):
   with self.assertRaises(ValueError):self.module().decode_job(wire)
 def test_unique_logical_metadata_depth_and_item_limits_prevent_expansion_bombs(self):
  module=self.module()
  with patch.object(module,'MAX_UNIQUE_IMAGE_BYTES',len(IMAGE)-1):
   with self.assertRaises(ValueError):module.decode_job(self.wire())
  with patch.object(module,'MAX_LOGICAL_IMAGE_BYTES',len(IMAGE)):
   with self.assertRaises(ValueError):module.decode_job(self.wire())
  with patch.object(module,'MAX_METADATA_BYTES',20):
   with self.assertRaises(ValueError):module.decode_job(self.wire({'image':{'$image':0},'title':'😀'*20}))
  deep={'image':{'$image':0}};cursor=deep
  for _ in range(42):cursor['nested']={};cursor=cursor['nested']
  with self.assertRaises(ValueError):module.decode_job(self.wire(deep))
  with patch.object(module,'MAX_ITEMS',10):
   with self.assertRaises(ValueError):module.decode_job(self.wire({'image':{'$image':0},'x':[0]*11}))
 def test_per_image_length_and_nonfinite_values_are_bounded(self):
  module=self.module()
  with patch.object(module,'MAX_IMAGE_BYTES',10):
   with self.assertRaises(ValueError):module.decode_job(self.wire())
  with self.assertRaises(ValueError):module.decode_job(self.wire({'image':{'$image':0},'x':float('nan')}))
 def test_metadata_counts_utf8_codepoints_and_json_escaping(self):
  module=self.module();text={'text':'中文😀\n"'};expected=len(json.dumps(text,ensure_ascii=False,separators=(',',':')).encode('utf8'))
  self.assertEqual(module.measure(text)['metadataBytes'],expected)
  with patch.object(module,'MAX_METADATA_BYTES',expected-1):
   with self.assertRaises(ValueError):module.measure(text)
 def test_ordinary_small_job_is_backward_compatible(self):
  job={'image':IMAGE,'original':IMAGE,'mode':'codex','resume':scene()};result=self.module().decode_job(job)
  self.assertEqual(result,job)
 def test_jobs_route_accepts_57_layers_exceeding_old_expanded_limit_after_dedup(self):
  import server
  big='data:image/png;base64,'+'QUJD'*350000
  doc=scene();ref={'$image':0}
  for key in ('source','originalSource','comparisonSource'):doc[key]=ref
  for item in [*doc['nodes'],*doc['recognition']['resumePendingNodes']]:item['src']=ref
  wire=self.wire({'image':ref,'original':ref,'resume':doc,'mode':'refine-selected','selectedIds':['0']},[big]);captured=[];ident=None
  self.assertGreater(len(big)*62,72000000)
  try:
   with patch.object(server.pool,'submit',side_effect=lambda *a:captured.append(a)):
    response=server.app.test_client().post('/jobs',json=wire,headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
   self.assertEqual(response.status_code,202,response.get_json());ident=response.get_json()['id']
   restored=captured[0][6]
   self.assertEqual(restored['nodes'][56]['src'],big);self.assertIs(restored['nodes'][0]['src'],restored['recognition']['resumePendingNodes'][0]['src'])
   self.assertEqual(captured[0][7],['0']);self.assertEqual(captured[0][4],'refine-selected')
  finally:
   if ident:server.jobs.pop(ident,None)
 def test_jobs_route_rejects_bad_references_before_queuing(self):
  import server
  with patch.object(server.pool,'submit',side_effect=AssertionError('invalid references cannot queue')):
   response=server.app.test_client().post('/jobs',json=self.wire({'image':{'$image':9}}),headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
  self.assertEqual(response.status_code,400);self.assertNotIn(IMAGE,response.get_data(as_text=True))
 def test_HTTP_oversize_is_json_and_preserves_actionable_error(self):
  import server
  with patch.dict(server.app.config,MAX_CONTENT_LENGTH=128):
   response=server.app.test_client().post('/jobs',data='x'*256,content_type='application/json',headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
  self.assertEqual(response.status_code,413);self.assertTrue(response.is_json);self.assertIn('error',response.get_json())
 def test_resume_recovery_metadata_types_and_pending_geometry_are_validated(self):
  import server
  for key,value in (('resumePendingNodes','bad'),('resumePendingNodes',[{**node('p'),'width':'huge'}]),('resumeGroups',[{'id':'g','children':'bad'}]),('resumeNodeOrder',[{}]),('pendingGenerationIds',[0]),('resumePlan',[])):
   doc=scene();doc['recognition'][key]=value
   with self.subTest(field=key),self.assertRaises(ValueError):server.validate_resume(doc)
 def test_real_frontend_encoder_roundtrips_into_actual_job_route(self):
  import hashlib,os,subprocess,tempfile,server
  from pathlib import Path
  root=Path(__file__).resolve().parents[2];node_exe=root/'依赖/运行环境/node/node.exe'
  if not node_exe.is_file():self.skipTest('bundled Node runtime unavailable')
  script=root.parent/'测试结果/拾界_工程容量_20261015/transport.test.cjs';ident=None;captured=[]
  try:
   with tempfile.TemporaryDirectory() as tmp:
    output=Path(tmp)/'wire.json';environment={**os.environ,'SHIJIE_TRANSPORT_FIXTURE':str(output)}
    run=subprocess.run([str(node_exe),str(script)],capture_output=True,text=True,encoding='utf8',env=environment,timeout=30)
    self.assertEqual(run.returncode,0,run.stderr);wire=json.loads(output.read_text('utf8'))
   with patch.object(server.pool,'submit',side_effect=lambda *a:captured.append(a)):
    response=server.app.test_client().post('/jobs',json=wire,headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
   self.assertEqual(response.status_code,202,response.get_json());ident=response.get_json()['id'];restored=captured[0][6]
   expected='data:image/png;base64,'+'QUJD'*350000
   self.assertEqual(hashlib.sha256(restored['nodes'][0]['src'].encode()).hexdigest(),hashlib.sha256(expected.encode()).hexdigest())
   self.assertEqual(len(restored['nodes']),57);self.assertEqual(len(restored['recognition']['resumePendingNodes']),57)
   self.assertTrue(restored['nodes'][0]['versionArchived']);self.assertEqual(captured[0][7],['20'])
   self.assertIs(restored['source'],restored['nodes'][0]['src']);self.assertIn('😀',restored['text'])
  finally:
   if ident:server.jobs.pop(ident,None)
 def test_health_advertises_loaded_wire_capability(self):
  import server
  with patch('codex_pipeline.requirements',return_value=[]),patch('codex_client.command',return_value=['fixture']):
   response=server.app.test_client().get('/health',headers={'X-Shijie-Token':server.TOKEN},base_url='http://127.0.0.1:19217')
  self.assertEqual(response.status_code,200);self.assertEqual(response.get_json().get('imageWireVersion'),1)

if __name__=='__main__':unittest.main()
