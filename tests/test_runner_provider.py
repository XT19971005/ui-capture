import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image


class RunnerProviderTests(unittest.TestCase):
    def test_saved_company_channel_survives_both_assistant_validations(self):
        root = Path(__file__).resolve().parents[1]
        image = io.BytesIO()
        Image.new('RGB', (20, 16), 'red').save(image, format='PNG')
        body = {'image':'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode(),
                'scene':{'width':20,'height':16,'nodes':[]},'selectedIds':[],
                'messages':[{'role':'user','content':'自动标注'}], 'provider':'auto',
                'model':'gpt-6.1-sol','annotationOnly':True,'annotationLimit':128}
        script = """
import json,os,sys
from pathlib import Path
from unittest.mock import patch
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'tools'),str(root),str(root/'legacy/拾界插件/开发源码/自动拆图')]
from tools import run_job
run_job.sys.argv=['run_job.py','controlled-provider-check','gpt-6.1-sol']
def model(prompt,images,schema,provider,model_id,*args,**kwargs):
    assert provider in ('auto','codex'), 'company routing must not inject an invalid public provider'
    assert run_job.CLIENT.company['key']=='controlled-company-key'
    return {'objects':[{'name':'测试文字','points':[[1,1],[10,1],[10,10],[1,10]],'layerType':'text'}]}
with patch('assistant_models.analyze',side_effect=model),patch.object(run_job.CLIENT,'ensure_ready',side_effect=AssertionError('must not use personal Codex login')):
    run_job.main()
"""
        with tempfile.TemporaryDirectory() as folder:
            task = Path(folder)
            (task/'input.json').write_text(json.dumps(body), encoding='utf8')
            env = {**os.environ,'SHIJIE_TASK_ROOT':folder,'SHIJIE_CONFIG':str(task/'absent.toml'),
                   'SHIJIE_DATA_ROOT':str(task/'data'),'SHIJIE_PRODUCTION':'0','PYTHONDONTWRITEBYTECODE':'1'}
            connection = {'analysisProvider':'company','company':{'key':'controlled-company-key'},
                          'needsCodex':False,'mode':'assistant-plan'}
            process = subprocess.run([sys.executable,'-I','-X','utf8','-B','-c',script,str(root)],
                                     cwd=root,env=env,input=json.dumps(connection),encoding='utf8',
                                     capture_output=True,timeout=20)
            self.assertEqual(process.returncode,0,process.stderr)
            receipt = json.loads((task/'finished.json').read_text(encoding='utf8'))
            diagnostic = json.loads((task/'failure.json').read_text(encoding='utf8')) if (task/'failure.json').exists() else {}
            self.assertEqual(receipt['status'],'completed',{'receipt':receipt,'diagnostic':diagnostic})
            result = json.loads((task/'result.json').read_text(encoding='utf8'))
            self.assertEqual(result['job']['annotationObjects'][0]['name'],'测试文字')
            self.assertEqual(json.loads((task/'input.json').read_text(encoding='utf8')),body)
