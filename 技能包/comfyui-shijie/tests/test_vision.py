import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vision import parse_advice, parse_names, load_local_expert_model


class VisionTests(unittest.TestCase):
    def test_weight_only_directory_receives_generation_config_before_model_load(self):
        calls=[]
        class Config:
            @staticmethod
            def from_pretrained(path,**kwargs):
                calls.append(('config',path,kwargs));return 'model-config'
        class Generation:
            @staticmethod
            def from_pretrained(path,**kwargs):
                calls.append(('generation',path,kwargs));return 'prepared-generation-config'
        class Model:
            @classmethod
            def from_pretrained(cls,path,**kwargs):
                calls.append(('model',path,kwargs))
                if kwargs.get('generation_config')!='prepared-generation-config':
                    raise TypeError('weight-only directory has no generation_config.json')
                return cls()
            def to(self,device):return self
            def eval(self):return self
        result=load_local_expert_model(Model,Config,Generation,'weights-only','verified-support','bf16','cuda')
        self.assertIsInstance(result,Model)
        self.assertEqual([c[0] for c in calls],['config','generation','model'])
        self.assertEqual(calls[1][1],'verified-support')
        self.assertEqual(calls[2][1],'weights-only')
        self.assertTrue(calls[2][2]['local_files_only'])
        self.assertFalse(calls[2][2]['trust_remote_code'])

    def test_variable_layer_count_from_model(self):
        for n in (5,13):
            plan=parse_advice('{"suggested_layer_count":'+str(n)+',"description":"poster objects","layer_count_reason":"actual content"}',24)
            self.assertEqual(plan['suggested_layer_count'],n)

    def test_fenced_json(self):
        self.assertEqual(parse_advice('```json\n{"suggested_layer_count":3,"description":"separate background"}\n```',24)['suggested_layer_count'],3)

    def test_invalid_model_advice_never_falls_back(self):
        for text in ('{}','{"suggested_layer_count":true,"description":"x"}','{"suggested_layer_count":99,"description":"x"}','{"suggested_layer_count":5}'):
            with self.assertRaises(ValueError):parse_advice(text,24)

    def test_names_cannot_inject_extra_lines(self):
        self.assertEqual(parse_names('{"names":["背景\\n装饰"]}',1),['背景 装饰'])

    def test_names_cover_every_actual_layer(self):
        self.assertEqual(parse_names('{"names":["背景","柔和阴影"]}',2),['背景','柔和阴影'])
        with self.assertRaises(ValueError):parse_names('{"names":["背景"]}',2)

if __name__=='__main__':unittest.main()
