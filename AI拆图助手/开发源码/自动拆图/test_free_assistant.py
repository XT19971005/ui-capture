import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class AutoAnnotationTests(unittest.TestCase):
 def test_fresh_asset_name_and_auto_apply_instructions_are_distinct_from_project_title(self):
  import free_assistant as f
  body=self.body();body.pop('annotationOnly');body.pop('annotationLimit')
  expected={'reply':'将生成新素材','action':'generate','instruction':'生成透明绿色宝石','targetIds':[],'reference':'original','name':'绿色宝石图标','layers':[]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=expected) as model:
   self.assertEqual(f.plan(body,Path(folder),lambda:False,lambda *_:None),expected)
   self.assertIn('generate和extract的name是本次新素材名称',model.call_args.args[0])
   self.assertIn('自动添加为新图层',model.call_args.args[0])
 def test_incomplete_subject_support_keeps_full_bag_and_reports_review_warning(self):
  from auto_annotations import refine_envelopes
  objects=[{'name':'完整主体','points':[[0,0],[100,0],[100,80],[0,80]]}]
  detections={'objects':[{'name':'完整主体','shape':'envelope'}]}
  with patch('assistant_models.analyze',return_value={'outlines':[{'index':0,'points':[[0,0],[100,0],[50,10]]}]}):
   result,warnings=refine_envelopes(copy.deepcopy(objects),detections,self.body(),[],[(0,0,1)],100,80,128,False,lambda:False,lambda *_:None)
   self.assertEqual(result,objects);self.assertEqual(warnings,['完整主体'])
 def test_outer_bag_uses_convex_supports_in_any_order_without_diagonal_cuts(self):
  from auto_annotations import support_envelope
  points=[[5,10],[18,2],[30,10],[25,28],[10,28],[12,12],[20,15]]
  contour=support_envelope(points,40,40,False)
  self.assertGreater(max(p[1] for p in contour),28);self.assertLess(min(p[0] for p in contour),5)
  from auto_annotations import validate_objects
  self.assertEqual(len(validate_objects({'objects':[{'name':'完整主体','points':contour}]},40,40,1)),1)
 def test_crop_coordinates_map_back_once_and_clamped_envelope_stays_valid(self):
  from auto_annotations import box_candidates
  result={'objects':[{'name':'小图标','box':[10,20,20,20],'shape':'rect','imageIndex':1}]}
  points=box_candidates(result,400,300,128,False,[(0,0,1),(100,50,2)])[0]['points']
  self.assertEqual(points,[[103,58],[117,58],[117,72],[103,72]])
  edge={'objects':[{'name':'完整主体','box':[0,0,100,100],'shape':'envelope'}]}
  self.assertEqual(len(box_candidates(edge,100,100,128,False,[(0,0,1)])[0]['points']),4)
 def test_independent_text_and_panel_may_share_bounds_without_being_same_object(self):
  from auto_annotations import box_candidates
  result={'objects':[{'name':'按钮底板','box':[2,2,10,6],'shape':'rect'},{'name':'按钮文字','box':[2,2,10,6],'shape':'rect'}]}
  self.assertEqual(len(box_candidates(result,20,16,128,False,[(0,0,1)])),2)
 def test_localized_box_review_and_generated_contours_do_not_slice_subject(self):
  import free_assistant as f
  first={'objects':[{'name':'完整战车','box':[2,1,16,14],'shape':'rect'}]}
  reviewed={'objects':[{'name':'完整战车','box':[-1,-1,22,18],'shape':'envelope'},{'name':'次数圆底','box':[2,10,3,3],'shape':'ellipse'}]}
  body={**self.body(),'annotationAllowExpand':True}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',side_effect=[first,reviewed,{'outlines':[{'index':0,'points':[[-1,-1],[21,-1],[21,17],[-1,17]]}]}]) as model:
   result=f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertEqual(model.call_count,3);self.assertEqual(len(model.call_args_list[1].args[1]),5)
   self.assertIn('局部放大复核',model.call_args_list[1].args[0]);self.assertEqual(list(Path(folder).iterdir()),[])
   car=result['annotationObjects'][0]['points'];self.assertLess(min(p[0] for p in car),-1);self.assertGreater(max(p[0] for p in car),21)
   self.assertLess(min(p[1] for p in car),-1);self.assertGreater(max(p[1] for p in car),17)
   self.assertGreaterEqual(len(car),4);self.assertEqual(len(result['annotationObjects'][1]['points']),24)
   self.assertEqual(result['action'],'discuss');self.assertEqual(result['layers'],[])
 def test_localized_review_failure_cleans_all_references_and_does_not_return_first_pass(self):
  import free_assistant as f
  first={'objects':[{'name':'主体','box':[1,1,10,10],'shape':'rect'}]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',side_effect=[first,RuntimeError('review failed')]),self.assertRaises(RuntimeError):
   try:f.plan(self.body(),Path(folder),lambda:False,lambda *_:None)
   finally:self.assertEqual(list(Path(folder).iterdir()),[])
 def test_detailed_inventory_exceeds_old_caps_and_survives_guide_validation(self):
  import free_assistant as f
  from source_annotations import validate
  import hashlib
  body={**self.body(),'annotationLimit':128}
  objects=[{'name':'独立控件'+str(i),'points':[[i*4+1,1],[i*4+3,1],[i*4+3,3],[i*4+1,3]]} for i in range(80)]
  body['image']=png(Image.new('RGB',(400,40),'red'));body['scene'].update(width=400,height=40)
  f.validate_request(body)
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value={'objects':objects}) as model:
   result=f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertEqual(len(result['annotationObjects']),80)
   for phrase in ('帮助图标','倒计时','数量文字','半透明底板','逐区扫描','不是要求凑满','完整徽章','铆钉','不是独立控件'):self.assertIn(phrase,model.call_args.args[0])
  state={'version':1,'width':400,'height':40,'sourceHash':hashlib.sha256(body['image'].encode()).hexdigest(),'items':[{'color':'#%06x'%(i+1),'label':o['name'],'strokes':[o['points']]} for i,o in enumerate(objects)]}
  self.assertEqual(len(validate(state,body['image'],400,40)['items']),80)
 def test_expanded_outline_roundtrips_through_annotation_validation(self):
  import free_assistant as f
  from source_annotations import validate
  import hashlib
  body={**self.body(),'annotationAllowExpand':True}
  output={'objects':[{'name':'完整战车','points':[[-3,-4],[23,-4],[23,20],[-3,20]]}]}
  f.validate_request(body)
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=output) as model:
   result=f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertEqual(result['annotationObjects'],output['objects'])
   for phrase in ('宽松包围','不要用最后一条闭合线','不是硬蒙版','底板','负坐标'):self.assertIn(phrase,model.call_args.args[0])
  state={'version':1,'width':20,'height':16,'sourceHash':hashlib.sha256(body['image'].encode()).hexdigest(),'allowExpand':True,'items':[{'color':'#ffdf24','label':'完整战车','strokes':[output['objects'][0]['points']]}]}
  self.assertIsNotNone(validate(state,body['image'],20,16))
  for changed in ({**body,'annotationAllowExpand':False},{**body,'annotationAllowExpand':0}):
   with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=output),self.assertRaises(ValueError):f.plan(changed,Path(folder),lambda:False,lambda *_:None)
 def test_no_recognized_objects_is_static_no_retry_result(self):
  import free_assistant as f
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value={'objects':[]}) as model:
   result=f.plan(self.body(),Path(folder),lambda:False,lambda *_:None)
   model.assert_called_once();self.assertEqual(result['annotationObjects'],[]);self.assertIn('未识别',result['reply']);self.assertEqual(result['action'],'discuss')
 def test_scope_discussion_preserves_selection_until_explicit_scope_change(self):
  import free_assistant as f
  body=self.body();body.pop('annotationOnly');body.pop('annotationLimit')
  body['messages']=[{'role':'user','content':'只拆标注1角色头部'},{'role':'assistant','content':'可以按选区拆分'},{'role':'user','content':'若整张拆分，还有什么替代方案？先讨论'}]
  expected={'reply':'这里的整图方案不是本轮授权范围，请先明确对象范围。','action':'discuss','instruction':'','targetIds':[],'reference':'original','name':'角色头部','layers':[],'nextStep':'discuss','choices':[]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=expected) as model:
   self.assertEqual(f.plan(body,Path(folder),lambda:False,lambda *_:None),expected)
   prompt=model.call_args.args[0]
   self.assertIn('若整张拆分',prompt);self.assertIn('不是本轮授权范围',prompt)
   self.assertIn('范围尚有歧义时action=discuss且nextStep=discuss',prompt)
   self.assertIn('用户最新明确变更范围时按新范围执行',prompt)
   self.assertIn('只拆标注1角色头部',prompt);self.assertIn('还有什么替代方案',prompt)
 def test_auto_provider_uses_existing_default_without_touching_image_models(self):
  import free_assistant as f
  body={**self.body(),'provider':'auto','model':''}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.objects()) as model:
   f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertIn(model.call_args.args[3],('auto','codex'));self.assertEqual(model.call_args.args[4],'')
 def test_explicit_tygpt_model_is_preserved_and_valid_triangle_accepted(self):
  import free_assistant as f
  body={**self.body(),'provider':'tygpt','model':'my-current-vision'}
  output={'objects':[{'name':'文字','points':[[1,1],[18,1],[1,14]],'category':'text'}]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=output) as model:
   result=f.plan(body,Path(folder),lambda:False,lambda *_:None)
   self.assertEqual(model.call_args.args[3:5],('tygpt','my-current-vision'));self.assertEqual(len(result['annotationObjects'][0]['points']),3)
 def test_false_flag_preserves_ordinary_assistant_validation_and_plan(self):
  import free_assistant as f
  body=self.body();body['annotationOnly']=False;body['scene']['width']=19
  expected={'reply':'只讨论','action':'discuss','instruction':'','targetIds':[],'reference':'original','name':'角色','layers':[]}
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=expected) as model:
   self.assertEqual(f.plan(body,Path(folder),lambda:False,lambda *_:None),expected)
   self.assertIs(model.call_args.args[2],f.SCHEMA)
 def body(self):
  return {'image':png(Image.new('RGB',(20,16),'red')),'scene':{'width':20,'height':16,'nodes':[]},'selectedIds':[],'messages':[{'role':'user','content':'自动标注主体'}],'provider':'codex','model':'vision','annotationOnly':True,'annotationLimit':2}
 def objects(self):return {'objects':[{'name':'角色','points':[[1,1],[18,1],[18,14],[1,14]]}]}
 def test_annotation_analysis_once_returns_readonly_candidate_and_native_metadata(self):
  import free_assistant as f,hashlib
  body=self.body();before=copy.deepcopy(body);status=lambda *_:None;cancel=lambda:False
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.objects()) as model:
   result=f.plan(body,Path(folder),cancel,status)
   model.assert_called_once();args=model.call_args.args
   self.assertEqual(args[3:7],('codex','vision',cancel,status));self.assertEqual(len(args[1]),1)
   for word in ('不得执行','不得生成图片','20','16'):self.assertIn(word,args[0])
   self.assertEqual(result['annotationObjects'],self.objects()['objects']);self.assertEqual(result['action'],'discuss');self.assertEqual(list(Path(folder).iterdir()),[])
   self.assertEqual(result['sourceHash'],hashlib.sha256(body['image'].encode()).hexdigest())
   self.assertEqual((result['width'],result['height']),(20,16));self.assertEqual(result['layers'],[]);self.assertEqual(result['targetIds'],[])
  self.assertEqual(body,before)
 def test_invalid_request_options_or_snapshot_rejected_before_analysis(self):
  import free_assistant as f
  changes=[{'annotationOnly':1},{'annotationOnly':'true'},{'annotationLimit':True},{'annotationLimit':0},{'annotationLimit':129},{'annotationLimit':1.5},{'scene':{'width':19,'height':16,'nodes':[]}},{'selectedIds':['a']},{'attachment':{'src':self.body()['image']}}]
  for change in changes:
   with self.subTest(change=change),patch('assistant_models.analyze') as model,self.assertRaises(ValueError):f.validate_request({**self.body(),**change})
   model.assert_not_called()
 def test_invalid_contours_never_return_candidate_or_mutate_request(self):
  import free_assistant as f
  contours=[[[1,1],[2,2]],[[1,1],[2,2],[3,3]],[[1,1],[18,14],[18,1],[1,14]],[[1,1],[18,1],[18,1],[1,14]],[[1,1],[float('nan'),1],[1,14]],[[1,1],[float('inf'),1],[1,14]],[[1,1],[21,1],[1,14]],[[1,1],[10**400,1],[1,14]],[[True,1],[18,1],[1,14]],[[1,1],[18,1],[1,14]]*22]
  invalid=[{'objects':[{'name':'角色','points':points}]} for points in contours]+[{'objects':self.objects()['objects']*3},{'objects':self.objects()['objects']*2},{'objects':[{'name':'','points':[[1,1],[18,1],[1,14]]}]},{'objects':self.objects()['objects'],'action':'generate'}]
  for output in invalid:
   body=self.body();before=copy.deepcopy(body)
   with self.subTest(output=output),tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=output) as model,self.assertRaises(ValueError):f.plan(body,Path(folder),lambda:False,lambda *_:None)
   model.assert_called_once();self.assertEqual(body,before)
 def test_cancel_before_or_after_analysis_returns_no_candidate(self):
  import free_assistant as f
  for after in (False,True):
   calls=[False,True] if after else [True]
   with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.objects()) as model,self.assertRaises(InterruptedError):f.plan(self.body(),Path(folder),lambda:calls.pop(0),lambda *_:None)
   self.assertEqual(model.call_count,int(after))

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

class TygptBackendTests(unittest.TestCase):
 def response(self,data=None,status=200):
  class Response:
   status_code=status
   def __enter__(self):return self
   def __exit__(self,*_):pass
   def json(self):return data
  return Response()
 def test_real_directory_is_used_without_fabricating_model_ids(self):
  import assistant_models as m
  for shape in ({'data':[{'id':'vision-model'}]},{'models':['vision-model']},{'list':[{'id':'vision-model'}]}):
   with patch('pathlib.Path.exists',return_value=True),patch.object(m,'gateway_key',return_value='private'),patch.object(m,'validate_pat'),patch('requests.get',return_value=self.response(shape)) as get:
    result=m.status('tygpt');self.assertEqual(result['models'],[{'id':'vision-model','name':'vision-model'}]);self.assertTrue(result['ready']);self.assertEqual(get.call_args.args[0],m.BASE+'/models');self.assertFalse(get.call_args.kwargs['allow_redirects'])
 def test_unconfigured_status_is_not_ready_without_network_or_desktop(self):
  import assistant_models as m
  with tempfile.TemporaryDirectory() as folder,patch.object(m,'CONFIG',Path(folder)/'missing.json'),patch('requests.get') as get:
   result=m.status('tygpt');self.assertFalse(result['ready']);self.assertEqual(result['models'],[]);get.assert_not_called()
 def test_agent_sync_call_embeds_files_and_uses_fresh_sender_without_retry(self):
  import assistant_models as m,base64,uuid
  with tempfile.TemporaryDirectory() as folder:
   image=Path(folder)/'参考.png';Image.new('RGB',(8,8),'red').save(image);senders=[]
   with patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',return_value=self.response({'content':'{"ok":true}','message':'错误状态不可用作答案'})) as post:
    for _ in range(2):
     self.assertEqual(m.tygpt_analyze('p',[image],{},'vision',lambda:False,lambda *_:None),{'ok':True})
     args=post.call_args;self.assertEqual(args.args[0],m.BASE+'/agent/chat');body=args.kwargs['json'];self.assertFalse(body['stream']);self.assertEqual(body['max_retries'],0);self.assertNotIn('reasoning_effort',body);self.assertEqual(base64.b64decode(body['files'][0]['file_base64']),image.read_bytes());self.assertEqual(body['files'][0]['file_name'],'参考.png');self.assertNotIn(str(image),body['message']);self.assertFalse(args.kwargs['allow_redirects']);senders.append(body['sender_id']);uuid.UUID(body['sender_id'])
    self.assertNotEqual(*senders);self.assertEqual(post.call_count,2)
 def test_request_failure_does_not_retry_or_leak_credentials(self):
  import assistant_models as m,requests
  with patch.object(m,'gateway_key',return_value='user-pat'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',side_effect=requests.ConnectionError('user-pat')) as post:
   with self.assertRaises(ValueError) as error:m.tygpt_analyze('p',[],{},'vision',lambda:False,lambda *_:None)
   self.assertNotIn('user-pat',str(error.exception));self.assertEqual(post.call_count,1)
 def test_save_pat_validates_models_before_dpapi_atomic_save(self):
  import assistant_models as m,json
  with tempfile.TemporaryDirectory() as folder,patch.object(m,'CONFIG',Path(folder)/'private.json'),patch.object(m,'protect',return_value='dpapi:protected') as protect,patch.object(m,'validate_pat') as auth,patch.object(m,'gateway_models',return_value=[{'id':'vision','name':'vision'}]) as models:
   result=m.save_key(' user-pat ');auth.assert_called_once_with('user-pat');self.assertEqual(result['provider'],'tygpt');models.assert_called_once_with('user-pat');protect.assert_called_once_with('user-pat');stored=m.CONFIG.read_text('utf8');self.assertNotIn('user-pat',stored);self.assertEqual(json.loads(stored),{'baseUrl':m.BASE,'keyEncrypted':'dpapi:protected'});self.assertFalse(m.CONFIG.with_suffix('.tmp').exists())
 def test_wrong_config_host_and_old_provider_are_rejected(self):
  import assistant_models as m,json
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'private.json';path.write_text(json.dumps({'baseUrl':'https://evil.test','keyEncrypted':'dpapi:any'}),encoding='utf8')
   with patch.object(m,'CONFIG',path),self.assertRaises(ValueError):m.gateway_key()
  with self.assertRaises(ValueError):m.analyze('p',[],{},'taishi','',lambda:False,lambda *_:None)
 def test_cancel_before_send_does_not_read_key_or_call_network(self):
  import assistant_models as m
  with patch('requests.post') as post,patch.object(m,'gateway_key') as key,self.assertRaises(InterruptedError):m.tygpt_analyze('p',[],{},'vision',lambda:True,lambda *_:None)
  key.assert_not_called();post.assert_not_called()

 def test_catalog_capabilities_are_preserved_and_visual_default_is_supported(self):
  import assistant_models as m
  catalog={'models':[{'id':'gpt-6.1-sol','name':'text','capabilities':{'image':False},'high_cost':True},{'id':'gpt-6-sol','name':'vision','capabilities':{'image':True},'reasoning_efforts':['low','medium']}]}
  with patch('pathlib.Path.exists',return_value=True),patch.object(m,'gateway_key',return_value='private'),patch.object(m,'validate_pat'),patch('requests.get',return_value=self.response(catalog)):
   result=m.status('tygpt');self.assertEqual(result['model'],'gpt-6-sol');self.assertFalse(result['models'][0]['capabilities']['image']);self.assertTrue(result['models'][0]['high_cost'])
  with patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=result['models']),patch('requests.post') as post,self.assertRaisesRegex(ValueError,'不支持图片'):m.tygpt_analyze('p',['unused.png'],{},'gpt-6.1-sol',lambda:False,lambda *_:None)
  post.assert_not_called()

 def test_rejected_pat_does_not_replace_saved_credentials(self):
  import assistant_models as m
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'private.json';target.write_text('existing encrypted config',encoding='utf8')
   with patch.object(m,'CONFIG',target),patch.object(m,'validate_pat'),patch.object(m,'gateway_models',side_effect=ValueError('PAT无权限')),patch.object(m,'protect') as protect,self.assertRaises(ValueError):m.save_key('new-pat')
   self.assertEqual(target.read_text('utf8'),'existing encrypted config');protect.assert_not_called();self.assertFalse(target.with_suffix('.tmp').exists())
 def test_api_error_body_is_not_exposed_and_no_automatic_retries(self):
  import assistant_models as m
  with patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',return_value=self.response({'error':'private upstream-details'},status=401)) as post:
   with self.assertRaises(ValueError) as error:m.tygpt_analyze('p',[],{},'vision',lambda:False,lambda *_:None)
   self.assertNotIn('private',str(error.exception));self.assertNotIn('upstream',str(error.exception));self.assertEqual(post.call_count,1)

 def test_production_endpoint_and_real_content_field_are_used(self):
  import assistant_models as m
  self.assertEqual(m.BASE,'https://zxty.tuyoo.com/aichat/v1')
  self.assertEqual(m._reply_text({'content':'{"color":"红色"}','model':'gpt-6.1-sol','requested_model':'gpt-6.1-sol','assistant_message_id':'id','session_id':'sid','message':'ignore'}),' {"color":"红色"}'.strip())
  with self.assertRaises(ValueError):m._reply_text({'message':'error','response':'unsupported field'})
  self.assertEqual(m._default_model([{'id':'gpt-6-sol','capabilities':{'image':True}},{'id':'gpt-6.1-sol','capabilities':{'image':True}}]),'gpt-6.1-sol')
 def test_pat_probe_is_exact_validation_error_and_never_a_generation(self):
  import assistant_models as m
  with patch('requests.post',return_value=self.response({'code':400,'message':'message 不能为空'},400)) as post:
   m.validate_pat('private');self.assertEqual(post.call_args.args[0],m.BASE+'/agent/chat');self.assertEqual(post.call_args.kwargs['json'],{'message':'','max_retries':0,'stream':False});self.assertFalse(post.call_args.kwargs['allow_redirects']);self.assertEqual(post.call_count,1)
  for status,body in [(401,{'message':'private'}),(400,{'code':401,'message':'message 不能为空'}),(200,{'code':400,'message':'message 不能为空'}),(400,{'code':400,'message':'其他参数错误'})]:
   with patch('requests.post',return_value=self.response(body,status)),self.assertRaises(ValueError):m.validate_pat('private')
 def test_public_catalog_cannot_make_invalid_pat_ready_or_replace_config(self):
  import assistant_models as m
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'private.json';target.write_text('old-private-config',encoding='utf8')
   with patch.object(m,'CONFIG',target),patch.object(m,'gateway_key',return_value='private'),patch.object(m,'validate_pat',side_effect=ValueError('无效PAT')),patch.object(m,'gateway_models') as models:
    with self.assertRaises(ValueError):m.status('tygpt')
    with self.assertRaises(ValueError):m.save_key('new-pat')
    models.assert_not_called();self.assertEqual(target.read_text('utf8'),'old-private-config')

 def test_reasoning_effort_uses_only_actual_supported_catalog_values(self):
  import assistant_models as m
  cases=[(['low','high','medium'],'medium'),(['low','high','max'],'low'),(['max','high'],'max'),([],None),(None,None),(['invalid value','unknown'],None)]
  for supported,expected in cases:
   selected={'id':'vision'}
   if supported is not None:selected['reasoning_efforts']=supported
   with self.subTest(supported=supported),patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[selected]),patch('requests.post',return_value=self.response({'content':'{"ok":true}'})) as post:
    m.tygpt_analyze('p',[],{},'vision',lambda:False,lambda *_:None);body=post.call_args.kwargs['json']
    if expected is None:self.assertNotIn('reasoning_effort',body)
    else:self.assertEqual(body['reasoning_effort'],expected)
 def test_http_status_errors_remain_accurate_sanitized_and_single_attempt(self):
  import assistant_models as m
  for code,label in [(401,'PAT'),(403,'权限'),(429,'限流')]:
   with self.subTest(code=code),patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',return_value=self.response({'content':'private raw-details'},code)) as post:
    with self.assertRaises(ValueError) as error:m.tygpt_analyze('p',[],{},'vision',lambda:False,lambda *_:None)
    self.assertIn(str(code),str(error.exception));self.assertIn(label,str(error.exception));self.assertNotIn('private',str(error.exception));self.assertNotIn('raw-details',str(error.exception));self.assertEqual(post.call_count,1)
   with patch('requests.get',return_value=self.response({'message':'private'},code)) as get:
    with self.assertRaises(ValueError) as error:m.gateway_models('private')
    self.assertIn(str(code),str(error.exception));self.assertIn(label,str(error.exception));self.assertNotIn('private',str(error.exception));self.assertEqual(get.call_count,1)
   with patch('requests.post',return_value=self.response({'message':'private'},code)) as post:
    with self.assertRaises(ValueError) as error:m.validate_pat('private')
    self.assertIn(str(code),str(error.exception));self.assertIn(label,str(error.exception));self.assertNotIn('private',str(error.exception));self.assertEqual(post.call_count,1)
 def test_timeout_is_distinct_and_never_retries_or_exposes_upstream_text(self):
  import assistant_models as m,requests
  with patch.object(m,'gateway_key',return_value='private'),patch.object(m,'gateway_models',return_value=[{'id':'vision'}]),patch('requests.post',side_effect=requests.Timeout('private raw-details')) as post:
   with self.assertRaises(ValueError) as error:m.tygpt_analyze('p',[],{},'vision',lambda:False,lambda *_:None)
   self.assertIn('超时',str(error.exception));self.assertIn('未自动重试',str(error.exception));self.assertNotIn('private',str(error.exception));self.assertEqual(post.call_count,1)

 def test_flask_models_and_key_only_expose_static_safe_tygpt_errors(self):
  import assistant_models as m,server
  client=server.app.test_client();headers={'X-Shijie-Token':server.TOKEN};base='http://127.0.0.1:19217'
  for error in [m._TygptError('TYGPT鉴权失败（HTTP 401）：PAT过期'),m._TygptError('TYGPT请求失败（HTTP 429）：服务限流'),m._TygptError('TYGPT PAT鉴权超时，未自动重试')]:
   with self.subTest(error=str(error)),patch.object(m,'status',side_effect=error):
    response=client.get('/assistant/models?provider=tygpt',headers=headers,base_url=base);self.assertEqual(response.status_code,503);self.assertEqual(response.json['error'],str(error))
   with patch.object(m,'save_key',side_effect=error):
    response=client.post('/assistant/key',json={'key':'private-pat'},headers=headers,base_url=base);self.assertEqual(response.status_code,400);self.assertEqual(response.json['error'],str(error))
  for error in [ValueError('private-pat'),RuntimeError('secret-key')]:
   with patch.object(m,'status',side_effect=error):
    response=client.get('/assistant/models?provider=tygpt',headers=headers,base_url=base);self.assertEqual(response.status_code,503);self.assertNotIn(str(error),response.json['error'])
   with patch.object(m,'save_key',side_effect=error):
    response=client.post('/assistant/key',json={'key':'private-pat'},headers=headers,base_url=base);self.assertEqual(response.status_code,400);self.assertNotIn(str(error),response.json['error'])
 def test_timeouts_are_marked_as_static_safe_errors_for_routes(self):
  import assistant_models as m,requests
  for method,call in [('get',lambda:m.gateway_models('private')),('post',lambda:m.validate_pat('private'))]:
   with patch('requests.'+method,side_effect=requests.Timeout('private-pat')):
    with self.assertRaises(m._TygptError) as error:call()
    self.assertIn('超时',str(error.exception));self.assertNotIn('private-pat',str(error.exception))

class DiscussionChoiceTests(FreeAssistantTests):
 def test_style_choices_are_discussion_not_permission_to_generate(self):
  import free_assistant as f
  result={**self.plan(),'action':'discuss','nextStep':'choose','choices':[{'label':'海岛风格','message':'细化夏日海岛风格'},{'label':'蒸汽风格','message':'细化蒸汽风格'}]}
  self.assertEqual(f.validate_plan(result,self.body())['nextStep'],'choose')
  with self.assertRaises(ValueError):f.validate_plan({**result,'action':'generate'},self.body())
 def test_incomplete_or_oversized_choices_never_become_generation_confirmation(self):
  import free_assistant as f
  base={**self.plan(),'action':'discuss','nextStep':'choose'}
  for choices in ([],[{'label':'唯一项','message':'细化'}],[{'label':'a','message':'x'}]*9):
   with self.subTest(choices=choices),self.assertRaises(ValueError):f.validate_plan({**base,'choices':choices},self.body())
 def test_model_receives_choice_and_short_selection_context_rules(self):
  import free_assistant as f
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.plan()) as analyze:
   f.plan(self.body(),Path(folder),lambda:False,lambda *_:None)
   prompt=analyze.call_args.args[0]
   self.assertIn('nextStep=choose',prompt);self.assertIn('仅选择方案不代表授权生图',prompt)
   self.assertIn('角色参考',prompt)

class ScopeIntentTests(FreeAssistantTests):
 def test_alternative_full_scene_plan_is_never_confirmation_of_current_marked_extraction(self):
  import free_assistant as f
  with tempfile.TemporaryDirectory() as folder,patch('assistant_models.analyze',return_value=self.plan()) as analyze:
   f.plan(self.body(),Path(folder),lambda:False,lambda *_:None)
   prompt=analyze.call_args.args[0]
   self.assertIn('若整张拆分',prompt);self.assertIn('不是本轮授权范围',prompt)
   self.assertIn('提取独立素材',prompt)
