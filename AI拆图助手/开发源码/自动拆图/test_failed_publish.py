import copy,unittest
from unittest.mock import patch
from test_continue_missing import ContinueMissingTests
from progressive_scene import completed_scene
from incremental_assets import recover_pending_scene

class FailedPublishTests(unittest.TestCase):
 def test_fallback_is_recoverable_but_never_visible_as_extracted_layer(self):
  case=ContinueMissingTests();case.setUp();scene=copy.deepcopy(case.previous)
  scene['nodes'][2].update(provenance='source-crop-fallback',reviewIssue='生成中断')
  result=completed_scene(scene)
  self.assertNotIn('old-a',[n['id'] for n in result['nodes']])
  self.assertEqual(result['recognition']['pendingGenerationIds'],['old-a'])
  recovered=recover_pending_scene(result)
  self.assertEqual(next(n for n in recovered['nodes'] if n['id']=='old-a')['src'],case.actor['src'])
 def test_final_result_stops_after_connection_failure_and_publishes_no_crop(self):
  case=ContinueMissingTests();case.setUp();previous=copy.deepcopy(case.previous)
  previous['nodes']=previous['nodes'][:2];previous['groups']=[]
  with patch('workflow_assets.complete_asset',side_effect=RuntimeError('Codex 连接中断，自动重连未成功，请稍后重试。')):
   # run_pipeline normally patches this entry, so supply its failing callback.
   def fail(node):raise RuntimeError('Codex 连接中断，自动重连未成功，请稍后重试。')
   result,generated,_=case.run_pipeline(previous=previous,generate=fail)
  self.assertEqual(len(generated),1,'must not submit every remaining image to a broken connection')
  self.assertFalse(any(n.get('provenance')=='source-crop-fallback' for n in result['nodes']))
  self.assertEqual(len(result['recognition']['pendingGenerationIds']),2)

if __name__=='__main__':unittest.main()
