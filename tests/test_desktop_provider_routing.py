import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('desktop_connections',Path(__file__).resolve().parents[1]/'tools/desktop_connections.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Routing(TestCase):
 def test_external_analysis_and_images_do_not_require_codex(self):
  class Assistant:
   @staticmethod
   def gateway_key():return 'fake-private-pat'
  class Images:
   @staticmethod
   def key():return 'fake-private-image-key'
  with patch.object(module,'load_connections',return_value=(Assistant,Images)):
   value=module.credentials(Path('.'),'tygpt',{'provider':'aimake','model':'gpt-image-2'},'assistant-plan')
  self.assertFalse(value['needsCodex']);self.assertEqual(value['analysisProvider'],'tygpt');self.assertEqual(value['image']['provider'],'aimake')
 def test_missing_connection_does_not_fall_back(self):
  with patch.object(module,'load_connections',return_value=None):
   with self.assertRaisesRegex(ValueError,'未改用Codex'):module.credentials(Path('.'),'tygpt',{'provider':'aimake','model':'gpt-image-2'},'assistant-plan')
 def test_codex_image_task_retains_codex_requirement(self):
  with patch.object(module,'load_connections',return_value=None):
   self.assertTrue(module.credentials(Path('.'),'codex',{'provider':'codex','model':'gpt-image-2'},'assistant-split')['needsCodex'])