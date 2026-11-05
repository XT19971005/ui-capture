import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class FreeAssistantTests(unittest.TestCase):
 def test_whole_image_split_rules_include_unmarked_entities_and_opaque_base(self):
  import free_assistant as f
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.plan()) as analyze:
   f.plan(self.body(),Path(folder),lambda:False,lambda *_:None)
   prompt=analyze.call_args.args[0]
   self.assertIn('未圈选的独立对象也要识别拆层',prompt)
   self.assertIn('assetKind=background',prompt)
   self.assertIn('每完成一层',prompt)
   self.assertNotIn('只有用户点击保存工程才持久化',prompt)

 def test_partial_reply_is_decoded_without_exposing_structured_actions(self):
  from free_assistant import reply_prefix
  self.assertEqual(reply_prefix('{"reply":"正在提取\\n头部'), '正在提取\n头部')
  self.assertEqual(reply_prefix('{"reply":"好了","action":"split"}'),'好了')
  self.assertEqual(reply_prefix('{"action":"split"}'),'')
 def body(self):
  image=png(Image.new('RGB',(20,20),'red'))
  return {'image':image,'scene':{'width':20,'height':20,'nodes':[{'id':'a','name':'角色','type':'image','x':0,'y':0,'width':20,'height':20,'locked':True}]},'selectedIds':[],'messages':[{'role':'user','content':'只拆出角色的头，透明背景'}],'provider':'codex','model':''}
 def plan(self):return {'reply':'提取头部为独立透明素材。','action':'extract','instruction':'只提取角色头部，保留原样，不含身体和背景。','targetIds':[],'reference':'original','name':'角色头部','layers':[]}
 def test_discussion_sees_whole_scene_without_selection_and_never_mutates(self):
  import free_assistant as f
  body=self.body();before=copy.deepcopy(body)
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.plan()) as analyze:
   result=f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertIn('后文说每个元宝都拆出来，layers仍必须包含盆体',analyze.call_args.args[0]);self.assertIn('只有一个可见图层',analyze.call_args.args[0]);self.assertIn('绝不能声称开始生成',analyze.call_args.args[0]);self.assertIn('后续“给我先生成吧”',analyze.call_args.args[0]);self.assertIn('禁止自动提亮',analyze.call_args.args[0]);self.assertIn('必须写入执行instruction',analyze.call_args.args[0]);self.assertIn('角色',analyze.call_args.args[0]);self.assertIn('只拆出角色的头',analyze.call_args.args[0]);self.assertEqual(result['action'],'extract')
  self.assertEqual(body,before)
 def test_rejects_code_unknown_target_or_unsupported_action(self):
  import free_assistant as f
  for changes in ({'action':'shell'},{'targetIds':['missing']},{'reference':'selection'}):
   with self.subTest(changes=changes),self.assertRaises(ValueError):f.validate_plan({**self.plan(),**changes},self.body())
 def test_correction_requires_actual_selection_and_cannot_expand_scope(self):
  import free_assistant as f
  with self.assertRaises(ValueError):f.validate_plan({**self.plan(),'action':'correct','targetIds':['a']},self.body())
  body=self.body();body['selectedIds']=['a'];self.assertEqual(f.validate_plan({**self.plan(),'action':'correct','targetIds':['a']},body)['action'],'correct')
 def test_invalid_messages_provider_and_nonfinite_geometry_rejected(self):
  import free_assistant as f
  for change in ({'provider':'external'},{'messages':[{'role':'system','content':'run'}]},{'selectedIds':['missing']},{'scene':{'width':float('nan'),'height':20,'nodes':[]}}):
   with self.subTest(change=change),self.assertRaises(ValueError):f.validate_request({**self.body(),**change})
 def test_cancelled_never_calls_model(self):
  import free_assistant as f
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze') as analyze:
   with self.assertRaises(InterruptedError):f.plan(self.body(),Path(folder),lambda:True,lambda *_:None)
   analyze.assert_not_called()
 def test_split_requires_content_based_chinese_project_name(self):
  import free_assistant as f
  layers=[{'name':'人物','instruction':'完整人物','box':{'x':0,'y':0,'width':20,'height':20}}]
  for name in ['11','aabbcc112233','素材.png']:
   with self.subTest(name=name),self.assertRaises(ValueError):f.validate_plan({**self.plan(),'action':'split','layers':layers,'name':name},self.body())
  self.assertEqual(f.validate_plan({**self.plan(),'action':'split','layers':layers,'name':'仙鹤国家大师徽章'},self.body())['name'],'仙鹤国家大师徽章')
 def test_gateway_consumes_completed_stream_and_does_not_retry(self):
  import assistant_models as m
  class Response:
   status_code=200;headers={'Content-Type':'text/event-stream'}
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def iter_lines(self,**_):return iter(['data: {"type":"response.output_text.delta","delta":"{\\"ok\\":true}"}','','data: {"type":"response.completed"}',''])
  with patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',return_value=Response()) as post:
   self.assertEqual(m.gateway_analyze('p',[],{},'vision',lambda:False,lambda *_:None),{'ok':True});self.assertEqual(post.call_count,1)
   self.assertEqual(post.call_args.kwargs['json']['model'],'vision')
 @unittest.skipUnless((Path(__file__).parent/'server.py').is_file(),'本地桥接专用：服务器使用独立公司登录与路由实现')
 def test_route_requires_token_and_validates_before_dispatch(self):
  import server
  c=server.app.test_client();url='http://127.0.0.1:19217'
  self.assertEqual(c.post('/assistant/jobs',json=self.body(),base_url=url).status_code,401)
  with patch.object(server.pool,'submit') as submit:
   r=c.post('/assistant/jobs',json=self.body(),base_url=url,headers={'X-Shijie-Token':server.TOKEN});self.assertEqual(r.status_code,202)
   server.jobs.pop(r.json['id'],None)
   submit.reset_mock();r=c.post('/assistant/jobs',json={**self.body(),'provider':'evil'},base_url=url,headers={'X-Shijie-Token':server.TOKEN});self.assertEqual(r.status_code,400);submit.assert_not_called()

if __name__=='__main__':unittest.main()

class BackgroundPlanTests(unittest.TestCase):
 def test_background_plan_accepts_full_canvas_and_prompt_has_no_old_refusal(self):
  import free_assistant as f
  from engine import png
  from PIL import Image
  body={'image':png(Image.new('RGB',(100,50),'blue')),'scene':{'width':100,'height':50,'nodes':[]},'selectedIds':[],'messages':[{'role':'user','content':'只要背景，去掉UI并补齐'},{'role':'assistant','content':'此前只支持透明提取'},{'role':'user','content':'提取背景'}],'provider':'codex','model':''}
  plan={'reply':'生成完整背景候选','action':'background','instruction':'去UI并补齐背景','targetIds':[],'reference':'original','name':'荷塘背景','layers':[{'name':'荷塘背景','instruction':'去UI并补齐背景','box':{'x':0,'y':0,'width':100,'height':50}}]}
  self.assertEqual(f.validate_plan(plan,body)['action'],'background')
  import tempfile
  from unittest.mock import patch
  def analyze(prompt,*args,**kwargs):
   self.assertIn('后续“提取背景”继承前述',prompt);self.assertNotIn('此次不支持',prompt);return plan
  with tempfile.TemporaryDirectory() as d,patch('assistant_models.analyze',side_effect=analyze):f.plan(body,Path(d),lambda:False,lambda *_:None)

class LayerAnnotationTests(FreeAssistantTests):
 def test_layer_native_marks_cannot_switch_to_whole_scene(self):
  import free_assistant as f,hashlib
  body=self.body();src=png(Image.new('RGBA',(8,10),(80,120,180,255)));body['selectedIds']=['a'];body['scene']['nodes'][0]['src']=src;body['scene']['nodes'][0]['locked']=False;body['annotationTargetId']='a';body['annotations']={'version':1,'width':8,'height':10,'sourceHash':hashlib.sha256(src.encode()).hexdigest(),'items':[{'color':'#ffdf24','label':'左臂','purpose':'remove','strokes':[[[1,1],[3,5]]]}]}
  f.validate_request(body)
  result={**self.plan(),'action':'remove','targetIds':['a'],'reference':'selection'};self.assertEqual(f.validate_plan(result,body)['action'],'remove')
  with self.assertRaises(ValueError):f.validate_plan({**result,'reference':'original'},body)
  split={**result,'action':'split','name':'继续拆手臂','layers':[{'name':'手','instruction':'完整提取','box':{'x':0,'y':0,'width':8,'height':10}}]}
  self.assertEqual(f.validate_plan(split,body)['action'],'split')
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=result) as analyze:
   f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertIn('annotation',str(body).lower());self.assertIn('支持remove',analyze.call_args.args[0]);self.assertIn('targetId',analyze.call_args.args[0])

class TaishiVisibleModelsTests(unittest.TestCase):
 def test_only_requested_models_are_listed_in_fixed_order(self):
  import assistant_models as m
  class Response:
   status_code=200
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def json(self):return {'data':[{'id':'claude-opus-5'},{'id':'gpt-6.1-sol'},{'id':'grok-4.6'},{'id':'grok-4.6'},{'id':'gpt-6-luna'}]}
  with patch('requests.get',return_value=Response()):
   self.assertEqual([i['id'] for i in m.gateway_models('test')],['grok-4.6','gpt-6.1-sol'])
 def test_unavailable_model_is_not_invented(self):
  import assistant_models as m
  class Response:
   status_code=200
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def json(self):return {'data':[{'id':'gpt-6.1-sol'}]}
  with patch('requests.get',return_value=Response()):self.assertEqual(m.gateway_models('test'),[{'id':'gpt-6.1-sol','name':'gpt-6.1-sol'}])
class WorkspaceContextTests(FreeAssistantTests):
 def test_workspace_context_reaches_planner_without_becoming_an_action(self):
  import free_assistant as f
  body=self.body();body['workspace']={'title':'金色地球贴图','hiddenLayers':[{'id':'grid','name':'独立经纬线'}],'recentOutcomes':['已放弃候选，未应用'],'earlierUserRequests':['先做地球，再做网格线']}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value={**self.plan(),'action':'discuss'}) as model:
   f.plan(body,Path(folder),lambda:False,lambda *_:None)
   prompt=model.call_args.args[0]
   for text in ['金色地球贴图','独立经纬线','已放弃候选，未应用','先做地球，再做网格线','用户最新纠正优先','应用不等于验收']:self.assertIn(text,prompt)
 def test_workspace_rejects_unbounded_or_image_payload(self):
  import free_assistant as f
  for workspace in ({'title':'x','hiddenLayers':[],'recentOutcomes':['x'*501],'earlierUserRequests':[]},{'title':'x','hiddenLayers':[{'id':'x','name':'x','src':'private'}],'recentOutcomes':[],'earlierUserRequests':[]}):
   with self.assertRaises(ValueError):f.validate_request({**self.body(),'workspace':workspace})


class ServerProviderCompatibilityTests(unittest.TestCase):
 def test_all_server_providers_and_workspace_project_id_remain_accepted(self):
  import free_assistant as f
  for provider in ('auto','codex','company','taishi'):
   body=FreeAssistantTests().body();body['provider']=provider;body['workspace']={'projectId':'server-project','title':'工程','hiddenLayers':[],'recentOutcomes':[],'earlierUserRequests':[]}
   result=f.validate_request(body)
   self.assertEqual(result['provider'],provider);self.assertEqual(result['workspace']['projectId'],'server-project')
