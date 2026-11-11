import hashlib
from unittest.mock import patch
from django.test import TestCase
from .test_service import Service,png
from shijie.pipeline.models import Job

class NewCapabilities(TestCase):
    def setUp(self):
        Service.setUp(self)
        self.client.defaults['HTTP_HOST']='testserver'
    send=Service.send

    def scene(self):
        return {'format':'shijie-scene','version':2,'width':4,'height':3,'nodes':[], 'source':png()}

    def marks(self):
        return {'version':1,'width':4,'height':3,'sourceHash':hashlib.sha256(png().encode()).hexdigest(),
                'items':[{'color':'#ff0000','label':'完整对象','strokes':[[[0,0],[2,2]]]}]}

    def test_annotated_split_keeps_source_identity(self):
        from shijie.pipeline.storage import read_scene,job_root
        with patch('shijie.pipeline.ai.status',return_value={'ok':True,'ready':True,'imageGeneration':True}):
            response=self.send('jobs',{'image':png(),'annotations':self.marks()})
        self.assertEqual(response.status_code,202,response.content)
        stored=read_scene(job_root(Job.objects.get(pk=response.json()['id']))/'input.json')
        self.assertEqual(stored['annotations'],self.marks())
        self.assertEqual(stored['image'],png())
        bad=self.marks();bad['sourceHash']='0'*64
        self.assertEqual(self.send('jobs',{'image':png(),'annotations':bad}).status_code,400)
        self.assertEqual(Job.objects.count(),1)

    def test_assistant_analysis_does_not_require_image_generation(self):
        value={'image':png(),'scene':{'width':4,'height':3,'nodes':[]},'selectedIds':[], 'messages':[{'role':'user','content':'先分析如何拆'}], 'provider':'codex','model':'test-model'}
        with patch('shijie.pipeline.ai.status',return_value={'ok':True,'ready':True,'imageGeneration':False,'models':[{'id':'test-model'}]}):
            response=self.send('assistant/jobs',value)
        self.assertEqual(response.status_code,202,response.content)
        job=Job.objects.get(pk=response.json()['id']);self.assertEqual(job.mode,'assistant-plan')
        self.assertEqual(self.other.get('/api/engine/jobs/'+str(job.pk)).status_code,404)
        self.assertNotIn('input',self.client.get('/api/engine/jobs/'+str(job.pk)+'?afterRevision=0').json())
        self.assertEqual(self.send('assistant/jobs',{**value,'provider':'../../private'}).status_code,400)
        self.assertEqual(Job.objects.count(),1)

    def test_new_capabilities_are_advertised(self):
        health=self.client.get('/api/engine/health').json()
        self.assertEqual(health.get('sourceAnnotationsVersion'),1)
        self.assertEqual(health.get('assistantVersion'),1)

    def test_model_keys_are_private_encrypted_and_change_only_after_successful_probe(self):
        from shijie.pipeline import providers
        with patch('assistant_models.gateway_models', return_value=[{'id':'gpt-6.1-sol','name':'gpt-6.1-sol'}]):
            response=self.send('assistant/key',{'key':'test-private-taishi-key'})
        self.assertEqual(response.status_code,200,response.content)
        self.assertNotIn('test-private-taishi-key',providers.path(self.a).read_text())
        self.assertNotIn('test-private-taishi-key',response.content.decode())
        self.assertEqual(providers.secret(self.a,'taishi'),'test-private-taishi-key')
        self.assertEqual(self.other.get('/api/engine/assistant/models?provider=taishi').json()['models'],[])
        with self.assertRaises(ValueError):providers.secret(self.b,'taishi')
        before=providers.path(self.a).read_bytes()
        with patch('assistant_models.gateway_models',side_effect=ValueError('连接失败')):
            self.assertEqual(self.send('assistant/key',{'key':'changed-invalid-key'}).status_code,400)
        self.assertEqual(providers.path(self.a).read_bytes(),before)
        Job.objects.create(owner=self.a,mode='assistant-plan',title='active')
        self.assertEqual(self.send('assistant/key',{'key':'another-key'}).status_code,400)
        self.assertEqual(providers.path(self.a).read_bytes(),before)

    def test_aimake_image_job_does_not_require_codex_and_freezes_its_provider(self):
        from shijie.pipeline.storage import read_scene,job_root
        from shijie.pipeline import providers
        import json
        with patch('image_provider.catalog',return_value=[{'id':'gpt-image-2','name':'GPT Image 2'}]):
            response=self.send('image-provider',{'provider':'aimake','model':'gpt-image-2','key':'test-private-matrix-key'})
        self.assertEqual(response.status_code,200,response.content)
        with patch('shijie.pipeline.ai.status',side_effect=AssertionError('Codex must not be needed')):
            response=self.send('assistant/split',{'image':png(),'width':4,'height':3,'title':'样例','projectId':'sample-project','layers':[{'name':'主体','instruction':'提取完整主体','box':{'x':0,'y':0,'width':4,'height':3}}]})
        self.assertEqual(response.status_code,202,response.content)
        snapshot=json.loads((job_root(Job.objects.get(pk=response.json()['id']))/'connection.json').read_text())
        self.assertEqual(snapshot['project'],'sample-project')
        self.assertEqual(snapshot['imageProvider'],'aimake');self.assertFalse(snapshot['needsCodex'])
        self.assertNotIn('key',snapshot)
        self.assertEqual(self.other.get('/api/engine/image-provider').json()['provider'],'codex')
        self.assertEqual(self.send('image-provider',{'provider':'codex','model':'gpt-image-2'}).status_code,400)

    def test_queue_excludes_busy_account_but_can_claim_an_independent_user(self):
        from shijie.pipeline.worker import claim,resources
        from shijie.pipeline.storage import write_json,job_root
        first=Job.objects.create(owner=self.a,mode='codex',title='a1')
        second=Job.objects.create(owner=self.a,mode='codex',title='a2')
        third=Job.objects.create(owner=self.b,mode='codex',title='b1')
        self.assertEqual(claim().pk,first.pk)
        self.assertEqual(claim(resources(first)).pk,third.pk)
        self.assertIsNone(claim(resources(first)|resources(third)))
        second.refresh_from_db();self.assertEqual(second.status,'queued')
        # Stateless API work can share an account, while same-project mutations remain serialized.
        write_json(job_root(second)/'connection.json',{'provider':'company','needsCodex':False,'project':'same'})
        fourth=Job.objects.create(owner=self.a,mode='assistant-split',title='a3')
        write_json(job_root(fourth)/'connection.json',{'provider':'company','needsCodex':False,'project':'same'})
        self.assertEqual(claim(resources(first)).pk,second.pk)
        self.assertIsNone(claim(resources(second)))

    def test_storage_download_pins_public_address_and_keeps_tls_hostname(self):
        import image_provider
        from unittest.mock import Mock
        response=Mock();pool=Mock();pool.urlopen.return_value=response
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('urllib3.HTTPSConnectionPool',return_value=pool) as factory:
            with image_provider.storage_request('GET','https://storage.example.test/object?signature=public') as actual:
                self.assertIs(actual,response)
            self.assertEqual(factory.call_args.args,('8.8.8.8',443))
            self.assertEqual(factory.call_args.kwargs['assert_hostname'],'storage.example.test')
            self.assertEqual(pool.urlopen.call_args.kwargs['headers'],{'Host':'storage.example.test'})
            self.assertFalse(pool.urlopen.call_args.kwargs['redirect']);self.assertFalse(pool.urlopen.call_args.kwargs['retries'])
        for address in ('127.0.0.1','169.254.169.254','10.1.2.3','::1','::ffff:127.0.0.1'):
            with patch('socket.getaddrinfo',return_value=[(2,1,6,'',(address,443))]),patch('urllib3.HTTPSConnectionPool') as factory:
                with self.assertRaises(ValueError):
                    with image_provider.storage_request('GET','https://storage.example.test/file'):pass
                factory.assert_not_called()

    def test_assistant_runner_persists_stream_and_plan_without_scene_session(self):
        import io,json,os,sys,tempfile
        from pathlib import Path
        from tools import run_job
        from shijie.pipeline.storage import write_scene,read_scene
        value={'image':png(),'scene':{'width':4,'height':3,'nodes':[]},'selectedIds':[], 'messages':[{'role':'user','content':'先分析'}], 'provider':'company','model':''}
        plan={'reply':'先提取主体，确认后才生成。','action':'discuss'}
        def respond(body,folder,cancelled,progress,on_text):
            self.assertTrue(folder.is_dir());on_text(plan['reply']);return plan
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_scene(root/'input.json',value)
            connection={'analysisProvider':'company','needsCodex':False,'company':{'api_key':'test-only'},'mode':'assistant-plan'}
            with patch.dict(os.environ,{'SHIJIE_TASK_ROOT':folder}),patch.object(sys,'argv',['run_job.py','example','']),patch.object(sys,'stdin',io.StringIO(json.dumps(connection))),patch('free_assistant.plan',side_effect=respond),patch.object(run_job.CLIENT,'close'),patch.object(run_job.CLIENT,'ensure_ready',side_effect=AssertionError('Codex must not be used')),patch.object(run_job.CLIENT,'company',None):
                run_job.main()
            self.assertEqual(read_scene(root/'result.json'),plan)
            self.assertEqual(json.loads((root/'reply.json').read_text())['text'],plan['reply'])
            self.assertEqual(json.loads((root/'finished.json').read_text())['status'],'completed')
            self.assertEqual(list(root.glob('assistant-*')),[])

    def test_outpaint_restores_original_center_and_does_not_retry_or_leak_temp_paths(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from engine import load_source
        from assistant_split import generate,validate
        value={'image':png(),'width':4,'height':3,'title':'扩建检查','backgroundOnly':True,'outpaint':True,'layers':[{'name':'背景','instruction':'只补上下面','box':{'x':0,'y':0,'width':4,'height':7}}]}
        def draw(prompt,refs,target,**kwargs):
            Image.new('RGBA',(4,7),(30,140,60,255)).save(target)
            return {'actualImageGeneration':True,'provider':'aimake','file':str(target)}
        with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=draw) as call:
            result=generate(value,Path(folder),lambda:False,lambda *_:None)
            self.assertEqual(call.call_count,1)
            with load_source(result['nodes'][0]['src']) as output,load_source(value['image']) as source:
                self.assertEqual(output.size,(4,7));self.assertEqual(output.crop((0,2,4,5)).tobytes(),source.tobytes())
                self.assertEqual(output.getpixel((0,0))[:3],(30,140,60))
            self.assertNotIn('file',result['nodes'][0]['generationRecord'])
            self.assertEqual(result['recognition']['reviewStatus'],'NOT_REVIEWED')
        with self.assertRaises(ValueError):validate({**value,'projectId':'../../other'})
        def transparent(prompt,refs,target,**kwargs):
            Image.new('RGBA',(4,7),(0,0,0,0)).save(target)
            return {'actualImageGeneration':True}
        with tempfile.TemporaryDirectory() as folder,patch('image_provider.CLIENT.generate',side_effect=transparent) as call:
            with self.assertRaisesRegex(ValueError,'透明区域'):generate(value,Path(folder),lambda:False,lambda *_:None)
            self.assertEqual(call.call_count,1)

    def test_generated_layers_with_edge_warnings_need_review_not_regeneration(self):
        import tempfile
        from pathlib import Path
        from assistant_split import generate
        layers=[{'name':name,'instruction':'完整提取','box':{'x':0,'y':0,'width':4,'height':3}} for name in ('人物','玻璃')]
        value={'image':png(),'width':4,'height':3,'title':'边缘风险','layers':layers}
        generated={'id':'person','type':'image','src':png(),'boundaryReviewRequired':True,'reviewIssue':'边缘需校对','assetReviewStatus':'NEEDS_REVIEW','generationRecord':{'actualImageGeneration':True}}
        snapshots=[]
        with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',return_value=generated) as call:
            result=generate(value,Path(folder),lambda:False,lambda *_:None,on_scene=snapshots.append)
        self.assertEqual(call.call_count,2)
        self.assertFalse(result.get('_partial'))
        self.assertEqual(result['recognition']['extractionStatus'],'COMPLETED')
        self.assertEqual(result['recognition']['reviewStatus'],'NEEDS_REVIEW')
        self.assertFalse(result['recognition'].get('pendingLayers'))
        self.assertEqual(result['nodes'],[generated,generated])
        self.assertEqual(snapshots[0]['recognition']['pendingLayers'],layers[1:])
        with tempfile.TemporaryDirectory() as folder,patch('incremental_assets.extract_once',side_effect=[generated,ValueError('生成失败')]):
            with self.assertRaises(ValueError) as failure:
                generate(value,Path(folder),lambda:False,lambda *_:None)
        partial=failure.exception.partial
        self.assertTrue(partial['_partial'])
        self.assertEqual(partial['nodes'],[generated])
        self.assertEqual(partial['recognition']['extractionStatus'],'INCOMPLETE')
        self.assertEqual(partial['recognition']['pendingLayers'],layers[1:])

    def test_poll_tolerates_replaced_streaming_file_without_cancelling_job(self):
        from pathlib import Path
        job=Job.objects.create(owner=self.a,mode='assistant-plan',title='stream',status='running')
        original=Path.read_text
        def changing(path,*args,**kwargs):
            if path.name=='reply.json':raise FileNotFoundError('snapshot being replaced')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',changing):
            response=self.client.get('/api/engine/jobs/'+str(job.pk))
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'running')
        self.assertNotIn('previewText',response.json())
        job.refresh_from_db();self.assertFalse(job.cancel_requested)

    def test_expanded_asset_preserves_png_bytes_and_reports_registration_or_edge_risks(self):
        import base64,tempfile
        from pathlib import Path
        from PIL import Image,ImageDraw
        from expanded_assets import register_asset
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'asset.png';image=Image.new('RGBA',(32,16));ImageDraw.Draw(image).rectangle((4,2,28,14),fill=(90,60,30,255));image.save(path)
            result=register_asset(path,64,(-16,-16))
            self.assertEqual(base64.b64decode(result['src'].split(',')[1]),path.read_bytes())
            self.assertEqual((result['width'],result['height']),(64,32))
            self.assertEqual((result['x'],result['y']),(-16,0))
            self.assertTrue(result['positionReviewRequired']);self.assertFalse(result['boundaryReviewRequired'])
            ImageDraw.Draw(image).point((0,8),fill=(1,2,3,255));image.save(path)
            self.assertTrue(register_asset(path,64,(0,0))['boundaryReviewRequired'])
            square=Image.new('RGBA',(16,16));ImageDraw.Draw(square).rectangle((4,4,12,12),fill=(90,60,30,255));square.save(path)
            self.assertFalse(register_asset(path,32,(0,0))['positionReviewRequired'])

    def test_chat_attachment_is_separate_from_project_and_cannot_target_edits(self):
        from free_assistant import validate_request, validate_plan
        value={'image':png(),'scene':{'width':4,'height':3,'nodes':[]},'selectedIds':[], 'messages':[{'role':'user','content':'讨论粘贴参考'}], 'provider':'company','model':'','attachment':{'src':png()},'workspace':{'projectId':'my-project','title':'测试','hiddenLayers':[],'recentOutcomes':[],'earlierUserRequests':[]}}
        self.assertEqual(validate_request(value)['attachment']['src'],png())
        plan={'reply':'先讨论','action':'discuss','instruction':'','targetIds':[],'reference':'attachment','name':'参考','layers':[]}
        self.assertEqual(validate_plan(plan,value)['action'],'discuss')
        for action in ('correct','split','remove','background','outpaint'):
            with self.assertRaises(ValueError):validate_plan({**plan,'action':action,'instruction':'修改'},value)

    def test_feedback_endpoint_is_private_idempotent_and_rejects_invalid_or_unsaved_requests(self):
        import json,uuid
        from pathlib import Path
        key=str(uuid.uuid4())
        value={'submissionKey':key,'category':'功能异常','description':'问题描述 token=secret-token-value','diagnostics':{'viewport':{},'errors':[],'actions':[]},'screenshot':png()}
        # Atomic POSIX fsync is covered by deployment tests; here isolate request/ownership behavior.
        def save(path,record):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(record),encoding='utf8')
        with patch('shijie.pipeline.storage.write_json',side_effect=save):
            first=self.send('feedback',value);self.assertEqual(first.status_code,201,first.content)
            again=self.send('feedback',value);self.assertEqual(again.status_code,200);self.assertEqual(first.json()['id'],again.json()['id'])
            other=self.send('feedback',value,client=self.other);self.assertEqual(other.status_code,201);self.assertNotEqual(first.json()['id'],other.json()['id'])
        records=list(Path(self.folder.name).glob('users/*/feedback/*.json'));self.assertEqual(len(records),2)
        self.assertNotIn('secret-token-value',records[0].read_text('utf8'))
        self.assertEqual(self.send('feedback',{**value,'submissionKey':'../../escape'}).status_code,400)
        self.assertEqual(self.send('feedback',{**value,'screenshot':'data:image/png;base64,broken'}).status_code,400)
        with patch('shijie.pipeline.storage.write_json',side_effect=OSError('disk full')):
            failure=self.send('feedback',{**value,'submissionKey':str(uuid.uuid4())});self.assertEqual(failure.status_code,507);self.assertNotIn('received',failure.json())
