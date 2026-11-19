import copy, unittest
from interaction_plan import validate_plan

class InteractionPlanTests(unittest.TestCase):
 def setUp(self):
  self.scene={'nodes':[{'id':'button','name':'STEAM愿望单'}]}
  self.behavior=dict(id='steam',label='愿望单',role='button',targetIds=['button'],enter='rise',idle='none',hover='lift',press='scale',action='feedback',message='下一页点击反馈',duration=500,delay=0)
 def test_exact_targets_and_safe_actions(self):
  plan={'version':1,'summary':'预约页','behaviors':[self.behavior]}
  self.assertEqual(validate_plan(plan,self.scene),plan)
  for change in ({'targetIds':['unknown']},{'action':'execute'},{'duration':False},{'delay':-1}):
   bad=copy.deepcopy(plan);bad['behaviors'][0].update(change)
   with self.assertRaises(ValueError):validate_plan(bad,self.scene)
 def test_duplicate_ownership_is_rejected(self):
  other={**self.behavior,'id':'other'}
  with self.assertRaises(ValueError):validate_plan({'version':1,'summary':'','behaviors':[self.behavior,other]},self.scene)

if __name__=='__main__':unittest.main()
