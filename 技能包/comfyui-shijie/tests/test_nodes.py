import sys,unittest,json
from pathlib import Path
import numpy as np
import tempfile,types
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nodes


class NodeContracts(unittest.TestCase):
    def test_mappings_and_required_functions(self):
        self.assertIn('ShijieReuseLayers',nodes.NODE_CLASS_MAPPINGS)
        for cls in nodes.NODE_CLASS_MAPPINGS.values():
            self.assertTrue(callable(getattr(cls(),cls.FUNCTION)))
            self.assertIn('required',cls.INPUT_TYPES())
            self.assertEqual(len(cls.RETURN_TYPES),len(cls.RETURN_NAMES))

    def test_expert_model_files_are_real_inputs_for_platform_downloads(self):
        schema=nodes.ShijieVisualExpert.INPUT_TYPES()
        for i in range(1):self.assertIn('model_file_'+str(i),schema['optional'])
        self.assertTrue(schema['optional']['model_file_0'][1]['default'].endswith('/model.safetensors'))

    def test_ocr_does_not_discard_batch(self):
        with self.assertRaises(ValueError):nodes.ShijieAnalyze().run(np.ones((2,16,16,3)),.85)

    def test_plan_is_json_not_executable(self):
        with self.assertRaises((ValueError,json.JSONDecodeError)):
            nodes.ShijiePlan().run('print(1)')

    def test_count_comes_from_plan_not_eight(self):
        self.assertEqual(nodes.ShijieLayerCount().run('{"suggested_layer_count":5}'),(5,))
        self.assertEqual(nodes.ShijieLayerCount().run('{"suggested_layer_count":13}'),(13,))
        with self.assertRaises(ValueError):nodes.ShijieLayerCount().run('{"texts":[]}')

    def test_output_node_returns_downloadable_file_descriptors(self):
        with tempfile.TemporaryDirectory() as temp:
            environment=types.SimpleNamespace(get_output_directory=lambda:temp)
            with patch.dict(sys.modules,{'folder_paths':environment}):
                result=nodes.ShijieNativePSD().run(np.ones((1,16,16,4)), '{"texts":[]}', '下载验证', '不重建文字', False, False)
            self.assertEqual(len(result['ui']['images']),1)
            self.assertTrue(result['ui']['files'][0]['filename'].endswith('.psd'))
            for f in result['ui']['images']+result['ui']['files']:
                self.assertTrue((Path(temp)/f['subfolder']/f['filename']).is_file())

if __name__=='__main__':unittest.main()
