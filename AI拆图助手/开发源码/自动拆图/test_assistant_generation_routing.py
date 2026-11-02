import unittest
from test_free_assistant import FreeAssistantTests
class GenerationRoutingTests(FreeAssistantTests):
 def test_surface_transformation_has_independent_generation_action(self):
  from free_assistant import validate_plan
  p={**self.plan(),'action':'generate','instruction':'把地球展开为2:1长方形贴图，左右无缝，不带网格线，先只生成地球层'}
  self.assertEqual(validate_plan(p,self.body())['action'],'generate')
