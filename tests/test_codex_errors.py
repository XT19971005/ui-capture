import base64
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from codex_client import CodexClient
from shijie.pipeline.storage import read_scene, write_scene
from .test_service import png


class CodexErrors(SimpleTestCase):
    def test_extraction_progress_advances_and_counts_only_pending_materials(self):
        from codex_pipeline import _process
        source=png();plan=dict(project_name='进度检查',assets=[],texts=[],vectors=[],groups=[],warnings=[])
        nodes=[dict(id=str(i),name='素材'+str(i),type='image',x=0,y=0,width=4,height=3,src=source,provenance='pending-image-generation',pendingGeneration=True) for i in range(3)]
        nodes[0].update(assetKind='background')
        scene=dict(format='shijie-scene',version=2,title='进度检查',width=4,height=3,source=source,nodes=nodes,groups=[],edges=[])
        for resume in (False,True):
            previous=copy.deepcopy(scene)
            previous['nodes'][0].update(provenance='codex-image-generation',pendingGeneration=False)
            previous['recognition']=dict(resumePlan=plan,sourceOriginalSHA256=hashlib.sha256(base64.b64decode(source.split(',')[1])).hexdigest(),resumePendingNodes=copy.deepcopy(nodes[1:]))
            events=[];during=[]
            def build(src,title,p,progress,cancelled):
                progress(1,'原生图层完成');return copy.deepcopy(scene)
            def extract(src,node,assets,structure,cancelled,original,on_status,**kwargs):
                on_status('正在复核：'+node['name']);during.append(events[-1])
                return {**node,'provenance':'codex-image-generation','pendingGeneration':False}
            def background(src,holder,*args,**kwargs):
                holder['nodes'][0]={**holder['nodes'][0],'provenance':'codex-image-generation','pendingGeneration':False}
            with self.subTest(resume=resume),tempfile.TemporaryDirectory() as folder,patch('codex_pipeline.CLIENT',Mock(analyze=Mock(return_value=plan))),patch('codex_pipeline.assemble',side_effect=lambda p,build,*a,**kw:(p,build(p))),patch('engine.build_scene',side_effect=build),patch('incremental_assets.extract_once',side_effect=extract),patch('workflow_assets.complete_background',side_effect=background):
                result=_process(source,'进度检查',lambda p,m:events.append((p,m)),lambda:False,source,folder,resume_scene=previous if resume else None)
            self.assertEqual(len(during),2)
            self.assertGreater(during[1][0],during[0][0])
            self.assertIn('1/2' if resume else '2/3',during[0][1])
            self.assertIn('2/2' if resume else '3/3',during[1][1])
            self.assertTrue(all(a[0]<=b[0] for a,b in zip(events,events[1:])),events)
            self.assertEqual(events[-1][0],1)
            if resume:self.assertEqual(result['nodes'][0],previous['nodes'][0])

    def test_status_and_partial_updates_do_not_reset_job_progress(self):
        from tools import run_job
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_scene(root/'input.json',{'image':png()});observed=[]
            def process(source,title,progress,cancelled,**kwargs):
                scene={'nodes':[{'id':'kept'}]}
                for amount,message in [(.4,'规划完成'),(0,'正在连接')]:
                    progress(amount,message);observed.append(json.loads((root/'progress.json').read_text())['progress'])
                kwargs['on_scene'](scene);observed.append(json.loads((root/'progress.json').read_text())['progress'])
                progress(.7,'下一阶段');observed.append(json.loads((root/'progress.json').read_text())['progress'])
                return scene
            with patch.dict(os.environ,{'SHIJIE_TASK_ROOT':folder,'CODEX_HOME':folder}),patch.object(sys,'argv',['run_job.py','test-job','test-model']),patch.object(sys,'stdin',io.StringIO('{}')),patch.object(run_job,'CLIENT',Mock()),patch('codex_pipeline.process',side_effect=process):run_job.main()
            self.assertEqual(observed,[.4,.4,.4,.7])
            self.assertEqual(read_scene(root/'partial.json')['nodes'],[{'id':'kept'}])
            self.assertEqual(json.loads((root/'finished.json').read_text())['status'],'completed')

    def test_failed_image_tool_reports_ip_denial_without_exposing_provider_text(self):
        from codex_client import CodexImageGenerationRequired
        client=CodexClient();client.ensure_ready=Mock();client.model=Mock(return_value='test-model')
        def rpc(method,params=None,**kwargs):
            if method=='thread/start':return {'thread':{'id':'test'}}
            if method=='turn/start':
                state=client.turns['test'];state['images'].append({'type':'imageGeneration','status':'failed','result':'','failure':{'message':'HTTP 401: Your IP is not authorized to make this request. private upstream payload'}})
                state['turn']={'status':'completed'};state['done'].set();return {'turn':{'id':'turn'}}
            return {}
        client.call=Mock(side_effect=rpc)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'kept.png';target.write_bytes(b'prior asset')
            with self.assertRaises(CodexImageGenerationRequired) as caught:client.generate('test',[],target)
            self.assertIn('IP',str(caught.exception));self.assertIn('401',str(caught.exception));self.assertNotIn('private',str(caught.exception));self.assertNotIn('额度',str(caught.exception))
            self.assertEqual(target.read_bytes(),b'prior asset')
        self.assertEqual(sum(c.args[0]=='turn/start' for c in client.call.call_args_list),1)

    def test_image_access_denial_stops_extraction_without_repeated_generation(self):
        from codex_client import CodexImageGenerationRequired
        from incremental_assets import extract_once,extract_checked
        node=dict(id='keep',name='素材',type='image',x=0,y=0,width=4,height=3)
        for extract in (extract_once,extract_checked):
            with self.subTest(extract=extract.__name__),tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'source.png';source.write_bytes(base64.b64decode(png().split(',')[1]));error=CodexImageGenerationRequired('IP 未获授权（401）')
                with patch('workflow_assets.complete_asset',side_effect=error) as generate,self.assertRaises(CodexImageGenerationRequired):extract(source,node,None,None,lambda:False,source,None)
                generate.assert_called_once()

    def test_failed_image_event_never_accepts_payload_or_leaks_failure(self):
        from codex_client import CodexImageGenerationRequired,CodexImageGenerationFailed
        for texts,expected in [(['Your IP is not authorized to make this request. private payload'],CodexImageGenerationRequired),([],CodexImageGenerationFailed)]:
            client=CodexClient();client.ensure_ready=Mock();client.model=Mock(return_value='test-model')
            def rpc(method,params=None,**kwargs):
                if method=='thread/start':return {'thread':{'id':'test'}}
                if method=='turn/start':
                    state=client.turns['test'];state['images'].append({'status':'failed','result':png().split(',')[1],'failure':'private payload'})
                    state['texts']=texts;state['turn']={'status':'completed'};state['done'].set();return {'turn':{'id':'turn'}}
                return {}
            client.call=Mock(side_effect=rpc)
            with self.subTest(texts=bool(texts)),tempfile.TemporaryDirectory() as folder:
                target=Path(folder)/'kept.png';target.write_bytes(b'prior asset')
                with self.assertRaises(expected) as caught:client.generate('test',[],target)
                self.assertNotIn('private',str(caught.exception));self.assertEqual(target.read_bytes(),b'prior asset')
                self.assertEqual('IP' in str(caught.exception),bool(texts))

    def test_runner_reports_explicit_image_failure_without_claiming_quota_or_access_denial(self):
        from tools import run_job
        from codex_client import CodexImageGenerationFailed
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_scene(root/'input.json',{'image':png()})
            with patch.dict(os.environ,{'SHIJIE_TASK_ROOT':folder,'CODEX_HOME':folder}),patch.object(sys,'argv',['run_job.py','test-job','test-model']),patch.object(sys,'stdin',io.StringIO('{}')),patch.object(run_job,'CLIENT',Mock()),patch('codex_pipeline.process',side_effect=CodexImageGenerationFailed()):run_job.main()
            result=json.loads((root/'finished.json').read_text());self.assertEqual(result['status'],'failed');self.assertIn('生图服务返回失败',result['message'])
            self.assertNotIn('额度',result['message']);self.assertNotIn('401',result['message']);self.assertFalse((root/'result.json').exists());self.assertEqual(read_scene(root/'input.json')['image'],png())

    def test_invalid_generated_image_never_overwrites_existing_asset(self):
        from PIL import Image
        sample = io.BytesIO()
        Image.new('RGBA', (4, 3), (100, 200, 0, 0)).save(sample, 'PNG')
        for payload, valid in [(b'', False), (b'not an image', False), (sample.getvalue(), True)]:
            client = CodexClient()
            client.ensure_ready = Mock()
            client.model = Mock(return_value='test-model')
            def rpc(method, params=None, **kwargs):
                if method == 'thread/start': return {'thread': {'id': 'test'}}
                if method == 'turn/start':
                    state = client.turns['test']
                    state['images'].append({'result': base64.b64encode(payload).decode()})
                    state['turn'] = {'status': 'completed'}
                    state['done'].set()
                    return {'turn': {'id': 'turn'}}
                return {}
            client.call = Mock(side_effect=rpc)
            with tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'kept.png'
                target.write_bytes(b'previous asset')
                if valid:
                    client.generate('test', [], target, transparent=True)
                    self.assertEqual(target.read_bytes(), payload)
                else:
                    with self.assertRaisesRegex(RuntimeError, '返回的图片为空或损坏'):
                        client.generate('test', [], target, transparent=True)
                    self.assertEqual(target.read_bytes(), b'previous asset')

    def failed_client(self, error):
        client = CodexClient()
        client.ensure_ready = Mock()
        client.model = Mock(return_value='test-model')

        def rpc(method, params=None, **kwargs):
            if method == 'thread/start':
                return {'thread': {'id': 'test-thread'}}
            if method == 'turn/start':
                state = client.turns['test-thread']
                state['turn'] = {'id': 'test-turn', 'status': 'failed', 'error': error}
                state['done'].set()
                return {'turn': {'id': 'test-turn'}}
            return {}

        client.call = Mock(side_effect=rpc)
        return client

    def quota_error(self):
        client = self.failed_client({'codexErrorInfo': 'usageLimitExceeded', 'message': 'private upstream payload'})
        with self.assertRaises(RuntimeError) as error:
            client.analyze('test', [], {})
        return error.exception

    def test_analysis_quota_is_actionable_without_repeating_provider_text(self):
        error = self.quota_error()
        self.assertIn('额度', str(error))
        self.assertIn('OpenAI', str(error))
        self.assertIn('usageLimitExceeded', str(error))
        self.assertNotIn('private', str(error))

    def test_generation_quota_does_not_retry_or_overwrite_existing_asset(self):
        client = self.failed_client({'codexErrorInfo': 'usageLimitExceeded', 'message': 'private upstream payload'})
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'kept.png'
            target.write_bytes(b'existing-asset')
            with self.assertRaises(RuntimeError) as error:
                client.generate('test', [], target)
            self.assertIn('额度', str(error.exception))
            self.assertNotIn('private', str(error.exception))
            self.assertEqual(target.read_bytes(), b'existing-asset')
        self.assertEqual(sum(call.args[0] == 'turn/start' for call in client.call.call_args_list), 1)

    def test_asset_extraction_stops_on_quota_without_crop_fallback_or_retry(self):
        from incremental_assets import extract_once, extract_checked
        error = self.quota_error()
        node = {'id': 'asset', 'name': 'kept', 'x': 0, 'y': 0, 'width': 4, 'height': 3}
        for extract in (extract_once, extract_checked):
            with self.subTest(extract=extract.__name__), tempfile.TemporaryDirectory() as folder, patch('workflow_assets.complete_asset', side_effect=error) as generate:
                source = Path(folder) / 'original.png'
                source.write_bytes(base64.b64decode(png().split(',', 1)[1]))
                with self.assertRaises(RuntimeError) as caught:
                    extract(source, node, None, None, lambda: False, None, None)
                self.assertIs(caught.exception, error)
                generate.assert_called_once()

    def test_runner_exposes_only_known_quota_and_retains_input_and_partial(self):
        from tools import run_job
        for code, known in (('usageLimitExceeded', True), ('other', False)):
            client = self.failed_client({'codexErrorInfo': code, 'message': 'private upstream payload'})
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                write_scene(root / 'input.json', {'image': png()})
                write_scene(root / 'partial.json', {'nodes': [{'id': 'kept'}]})
                with patch.dict(os.environ, {'SHIJIE_TASK_ROOT': folder, 'CODEX_HOME': folder}), patch.object(sys, 'argv', ['run_job.py', 'test-job', 'test-model']), patch.object(sys, 'stdin', io.StringIO('{}')), patch.object(run_job, 'CLIENT', client), patch('codex_pipeline.CLIENT', client):
                    run_job.main()
                result = json.loads((root / 'finished.json').read_text())
                self.assertEqual(result['status'], 'failed')
                self.assertEqual('额度' in result['message'], known)
                self.assertNotIn('private', result['message'])
                self.assertEqual(read_scene(root / 'input.json')['image'], png())
                self.assertEqual(read_scene(root / 'partial.json')['nodes'], [{'id': 'kept'}])
                self.assertFalse((root / 'result.json').exists())

    def test_runner_exposes_ip_denial_and_preserves_original_and_partial(self):
        from tools import run_job
        client=self.failed_client({'message':'HTTP 401: Your IP is not authorized to make this request. private payload'})
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_scene(root/'input.json',{'image':png()});write_scene(root/'partial.json',{'nodes':[{'id':'kept'}]})
            with patch.dict(os.environ,{'SHIJIE_TASK_ROOT':folder,'CODEX_HOME':folder}),patch.object(sys,'argv',['run_job.py','test-job','test-model']),patch.object(sys,'stdin',io.StringIO('{}')),patch.object(run_job,'CLIENT',client),patch('codex_pipeline.CLIENT',client):run_job.main()
            result=json.loads((root/'finished.json').read_text())
            self.assertEqual(result['status'],'failed');self.assertIn('IP',result['message']);self.assertNotIn('private',result['message']);self.assertNotIn('额度',result['message'])
            self.assertEqual(read_scene(root/'input.json')['image'],png());self.assertEqual(read_scene(root/'partial.json')['nodes'],[{'id':'kept'}]);self.assertFalse((root/'result.json').exists())
