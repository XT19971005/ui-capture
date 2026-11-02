import unittest,tempfile,copy
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from engine import png

class DialogueTests(unittest.TestCase):
 def scene(self):
  raw=png(Image.new('RGBA',(20,20),'red'))
  return raw,{'format':'shijie-scene','version':2,'width':20,'height':20,'source':raw,'originalSource':raw,'nodes':[{'id':'a','name':'龙尾','type':'image','x':0,'y':0,'width':20,'height':20,'src':raw}],'edges':[]}
 def test_route_forwards_dialogue_and_rejects_invalid_before_queue(self):
  import server
  raw,scene=self.scene();client=server.app.test_client();headers={'X-Shijie-Token':server.TOKEN};url='http://127.0.0.1:19217'
  body={'image':raw,'mode':'refine-selected','resume':scene,'selectedIds':['a'],'dialogue':{'action':'discuss','messages':[{'role':'user','content':'尾巴哪里错了'}]}}
  with patch.object(server.pool,'submit') as submit:
   result=client.post('/jobs',json=body,headers=headers,base_url=url);self.assertEqual(result.status_code,202)
   try:self.assertEqual(submit.call_args.kwargs['dialogue'],body['dialogue'])
   finally:server.jobs.pop(result.json['id'],None)
   submit.reset_mock();body['dialogue']['messages'][0]['role']='system'
   result=client.post('/jobs',json=body,headers=headers,base_url=url);self.assertEqual(result.status_code,400);submit.assert_not_called()
 def test_correction_instructions_reach_review_model(self):
  import selected_refine
  raw,scene=self.scene()
  with tempfile.TemporaryDirectory() as tmp,patch('acceptance.review_asset',return_value={'status':'PASS','issues':[]}) as review:
   result=selected_refine._process(raw,'test',lambda *_:None,lambda:False,raw,Path(tmp),scene,['a'],dialogue={'action':'correct','messages':[{'role':'user','content':'保留尾巴原来的颜色'}]})
   self.assertIn('保留尾巴原来的颜色',review.call_args.kwargs['user_request']);self.assertEqual({k:result['nodes'][0][k] for k in scene['nodes'][0]},scene['nodes'][0])
 def test_validation_rejects_roles_actions_and_oversized_messages(self):
  from selected_dialogue import validate_dialogue
  for v in [{'action':'execute','messages':[]},{'action':'discuss','messages':[{'role':'system','content':'x'}]},{'action':'discuss','messages':[{'role':'user','content':'x'*4001}]}]:
   with self.assertRaises(ValueError):validate_dialogue(v)
 def test_discussion_is_read_only_and_receives_selected_context_and_history(self):
  from selected_dialogue import discuss
  raw=png(Image.new('RGBA',(20,20),'red'));scene={'width':20,'height':20,'nodes':[{'id':'a','name':'龙尾','type':'image','x':0,'y':0,'width':20,'height':20,'src':raw},{'id':'b','name':'未选物件','type':'image','src':raw}]}
  before=copy.deepcopy(scene);reply={'reply':'尾巴被截断了，可以按原图补全。','canCorrect':True,'instruction':'补全龙尾并保持颜色和大小'}
  with tempfile.TemporaryDirectory() as tmp,patch('codex_client.CLIENT.analyze',return_value=reply) as model:
   result=discuss(Path(tmp)/'原图.png',scene,[scene['nodes'][0]],{'action':'discuss','messages':[{'role':'user','content':'尾巴不完整'}]},Path(tmp),lambda:False,lambda *_:None)
   prompt=model.call_args.args[0];self.assertIn('尾巴不完整',prompt);self.assertIn('龙尾',prompt);self.assertNotIn('未选物件',prompt)
  self.assertEqual(result,reply);self.assertEqual(scene,before)
