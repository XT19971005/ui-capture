import base64
import json
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.contrib.auth.models import Group
from PIL import Image
from shijie.accounts.models import User
from shijie.pipeline.models import Job
from shijie.pipeline import company
import company_agent as agent

SCHEMA = {'type': 'object', 'required': ['answer'], 'additionalProperties': False,
          'properties': {'answer': {'type': 'string'}}}
CONFIG = {'api_key': 'private-company-key', 'model': 'grok-4.6'}


class Reply:
    def __init__(self, wire, status=200, kind='text/event-stream'):
        self.wire, self.status_code = wire, status
        self.headers = {'content-type': kind}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size):
        yield from self.wire


class Protocol(SimpleTestCase):
    def send(self, reply):
        mock = patch('company_agent.requests.Session')
        session = mock.start().return_value.__enter__.return_value
        self.addCleanup(mock.stop)
        session.post.return_value = reply
        return session

    def test_sse_final_is_not_appended_to_deltas_and_utf8_can_split(self):
        content = json.dumps({'answer': '你好'}, ensure_ascii=False)
        wire = 'event: delta\r\ndata: {"content":"partial"}\r\n\r\n: heartbeat\n\nevent: done\ndata: ' + json.dumps({'content': content}, ensure_ascii=False) + '\n\n'
        session = self.send(Reply([bytes([b]) for b in wire.encode()]))
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / 'test.png'
            Image.new('RGB', (4, 4), 'blue').save(file)
            result = agent.analyze(CONFIG, '分析', [file], SCHEMA, root=Path(root))
        self.assertEqual(result, {'answer': '你好'})
        args, kwargs = session.post.call_args
        self.assertEqual(args, (agent.ENDPOINT,))
        self.assertFalse(session.trust_env)
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer ' + CONFIG['api_key'])
        self.assertTrue(kwargs['json']['stream'])
        self.assertEqual(kwargs['json']['files'][0]['file_type'], 'image/png')
        self.assertTrue(base64.b64decode(kwargs['json']['files'][0]['file_base64']).startswith(b'\x89PNG'))
        self.assertNotIn(CONFIG['api_key'], json.dumps(kwargs['json']))
        session.post.assert_called_once()

    def test_json_response_is_consumed_without_another_submission(self):
        session = self.send(Reply([b'{"content":"{\\"answer\\":\\"yes\\"}"}'], kind='application/json'))
        self.assertEqual(agent.analyze(CONFIG, '分析', [], SCHEMA, root=Path('/tmp')), {'answer': 'yes'})
        session.post.assert_called_once()

    def test_errors_incomplete_stream_and_oversize_are_safe_and_never_retried(self):
        for reply in [Reply([b'event: delta\ndata: {"content":"private"}\n\n']),
                      Reply([b'event: error\ndata: {"message":"private-key"}\n\n']),
                      Reply([b'x' * (2 * 1024 * 1024 + 1)]),
                      Reply([b'private-key'], status=401), Reply([], status=302),
                      Reply([b'{"content":42}'], kind='application/json')]:
            with self.subTest(status=reply.status_code):
                session = self.send(reply)
                with self.assertRaises(agent.CompanyError) as caught:
                    agent.analyze(CONFIG, '分析', [], SCHEMA, root=Path('/tmp'))
                self.assertNotIn('private', str(caught.exception))
                session.post.assert_called_once()

    def test_invalid_output_paths_cancel_and_attachment_limit_fail_closed(self):
        session = self.send(Reply([b'{"content":"{\\"answer\\":true}"}'], kind='application/json'))
        with self.assertRaises(agent.CompanyError):
            agent.analyze(CONFIG, '分析', [], SCHEMA, root=Path('/tmp'))
        session.post.reset_mock()
        for files in [[Path('/etc/passwd')], [Path('/tmp/a')] * 9]:
            with self.assertRaises(agent.CompanyError):
                agent.analyze(CONFIG, '分析', files, SCHEMA, root=Path('/tmp'))
        with self.assertRaises(InterruptedError):
            agent.analyze(CONFIG, '分析', [], SCHEMA, root=Path('/tmp'), cancelled=lambda: True)
        session.post.assert_not_called()

    def test_schema_limits_nullability_and_required_fields(self):
        from design_properties import nullable
        schema = nullable({'type': 'array', 'maxItems': 2, 'items': {'type': 'integer', 'minimum': 0}})
        for value in [None, [], [0, 1]]:
            agent.validate_result(value, schema)
        for value in [[True], [-1], [0, 1, 2], 'private', [float('nan')]]:
            with self.assertRaises(agent.CompanyError): agent.validate_result(value, schema)
        for value in [{}, {'answer': 'ok', 'extra': 'no'}]:
            with self.assertRaises(agent.CompanyError): agent.validate_result(value, SCHEMA)

    def test_company_failure_is_not_replayed_by_asset_refinement(self):
        from incremental_assets import extract_checked
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'source.png'
            Image.new('RGB', (8, 8), 'red').save(source)
            node = {'id':'asset', 'name':'test', 'type':'image', 'x':0, 'y':0, 'width':8, 'height':8}
            with patch('workflow_assets.complete_asset', side_effect=agent.CompanyError('公司图像工具暂不可用')) as call:
                result = extract_checked(source, node, root, root, lambda: False, source, None)
            call.assert_called_once()
            self.assertEqual(result['provenance'], 'source-crop-fallback')
            self.assertEqual(result['assetReviewStatus'], 'NEEDS_REVIEW')
            self.assertNotIn('actualImageGeneration', result)

    def test_company_generation_uses_the_selected_service_without_codex(self):
        from codex_client import CodexClient
        client = CodexClient()
        client.company = CONFIG
        result = {'file': '/tmp/generated.png', 'actualImageGeneration': True}
        with patch.object(client, 'call', side_effect=AssertionError('must not start Codex')), patch('company_agent.generate', create=True, return_value=result) as generate:
            self.assertEqual(client.generate('extract', [], '/tmp/generated.png', transparent=True), result)
            generate.assert_called_once()
            self.assertTrue(generate.call_args.kwargs['transparent'])

    def test_company_edit_rejection_is_actionable_without_echoing_provider_text(self):
        content = '图片编辑未成功：图片 API 返回 400 错误。private-company-key'
        session = self.send(Reply([json.dumps({'content': content}).encode()], kind='application/json'))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(agent.CompanyError) as caught:
                agent.generate(CONFIG, 'extract', [], Path(folder) / 'out.png', root=Path(folder))
        self.assertIn('HTTP 400', str(caught.exception))
        self.assertIn('附件', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))
        session.post.assert_called_once(); session.get.assert_not_called()

    def test_company_generation_downloads_real_image_once_and_normalizes_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'result.png'
            jpeg = io.BytesIO(); Image.new('RGB', (8, 8), 'red').save(jpeg, 'JPEG')
            content = '[下载生成图片](https://zxty.tuyoo.com/aichat/v1/workspace/715/download?path=gen_image%2Ftest.jpeg)'
            wire = ('event: done\ndata: ' + json.dumps({'content': content}) + '\n\n').encode()
            session = self.send(Reply([wire]))
            session.get.return_value = Reply([jpeg.getvalue()], kind='image/jpeg')
            result = agent.generate(CONFIG, 'generate', [], target, root=root)
            self.assertTrue(result['actualImageGeneration'])
            self.assertEqual(result['provider'], 'company')
            with Image.open(target) as image: self.assertEqual(image.format, 'PNG')
            session.post.assert_called_once(); session.get.assert_called_once()
            self.assertEqual(session.get.call_args.kwargs['headers']['Authorization'], 'Bearer ' + CONFIG['api_key'])
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_unsafe_download_links_are_rejected_before_sending_credentials(self):
        links = ['http://zxty.tuyoo.com/aichat/v1/workspace/1/download?path=gen_image/x.png',
                 'https://evil.test/x.png', 'https://zxty.tuyoo.com@evil.test/x.png',
                 'https://zxty.tuyoo.com/aichat/v1/workspace/1/download?path=../auth.json',
                 'https://zxty.tuyoo.com/aichat/v1/workspace/1/download?path=gen_image%2F..%2Fx.png',
                 'https://zxty.tuyoo.com/aichat/v1/workspace/1/download?path=private%2Fsecret.png',
                 'https://zxty.tuyoo.com/aichat/v1/workspace/1/download?path=gen_image/x.png&token=secret']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for url in links:
                with self.subTest(url=url):
                    session = self.send(Reply([json.dumps({'content': '[image](' + url + ')'}).encode()], kind='application/json'))
                    with self.assertRaises(agent.CompanyError): agent.generate(CONFIG, 'generate', [], root / 'out.png', root=root)
                    session.get.assert_not_called()

    def test_generation_keeps_existing_target_on_invalid_or_nontransparent_image(self):
        opaque = io.BytesIO(); Image.new('RGB', (8, 8), 'white').save(opaque, 'PNG')
        empty = io.BytesIO(); Image.new('RGBA', (8, 8), (0,0,0,0)).save(empty, 'PNG')
        content = '[下载](https://zxty.tuyoo.com/aichat/v1/workspace/715/download?path=gen_image%2Ftest.png)'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / 'kept.png'
            for raw in [opaque.getvalue(), empty.getvalue(), b'not-an-image']:
                target.write_bytes(b'original')
                session = self.send(Reply([json.dumps({'content': content}).encode()], kind='application/json'))
                session.get.return_value = Reply([raw], kind='image/png')
                with self.assertRaises(agent.CompanyError): agent.generate(CONFIG, 'extract', [], target, transparent=True, root=root)
                self.assertEqual(target.read_bytes(), b'original')
                session.post.assert_called_once()
            output = io.BytesIO(); picture = Image.new('RGBA', (8,8), (0,0,0,0)); picture.putpixel((3,3),(255,0,0,255)); picture.save(output,'PNG')
            session = self.send(Reply([json.dumps({'content': content}).encode()], kind='application/json'))
            session.get.return_value = Reply([output.getvalue()], kind='image/png')
            self.assertTrue(agent.generate(CONFIG, 'extract', [], target, transparent=True, root=root)['transparent'])

    def test_client_routes_analysis_and_readiness_to_company(self):
        from codex_client import CodexClient
        client = CodexClient()
        client.company = CONFIG
        with patch.object(client, 'account', return_value={'ready': False}) as account, patch('company_agent.analyze', return_value={'answer': 'ok'}) as call:
            client.ensure_ready()
            self.assertEqual(client.model(), CONFIG['model'])
            self.assertEqual(client.analyze('分析', [], SCHEMA), {'answer': 'ok'})
            call.assert_called_once()
            account.assert_not_called()
            client.ensure_ready(require_images=True)
            account.assert_not_called()


class Connections(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        override = override_settings(DATA_ROOT=Path(tmp.name), MIN_FREE=1)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user(username='company', email='one@example.test')
        self.other = User.objects.create_user(username='other', email='two@example.test')
        self.user.groups.add(Group.objects.get_or_create(name='使用者')[0])
        self.client.force_login(self.user)

    def post(self, value, route='connection', **kwargs):
        return self.client.post('/api/engine/company/' + route, json.dumps(value), content_type='application/json', HTTP_HOST='testserver', **kwargs)

    def test_credentials_encrypted_per_user_and_never_echoed(self):
        response = self.post({**CONFIG, 'enabled': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['configured'])
        self.assertFalse(response.json()['verified'])
        self.assertNotIn(CONFIG['api_key'], response.content.decode())
        self.assertNotIn(CONFIG['api_key'], company.path(self.user).read_text())
        self.assertEqual(company.path(self.user).stat().st_mode & 0o777, 0o600)
        self.assertEqual(company.credentials(self.user)['api_key'], CONFIG['api_key'])
        self.assertIsNone(company.credentials(self.other))
        self.assertFalse(company.status(self.other)['configured'])
        self.assertIn('no-store', self.client.get('/api/engine/company/connection')['Cache-Control'])

    def test_blank_key_preserves_secret_and_disable_switches_back_to_codex(self):
        self.post({**CONFIG, 'enabled': True})
        self.assertEqual(self.post({'api_key': '', 'model': 'grok-other', 'enabled': False}).status_code, 200)
        self.assertIsNone(company.credentials(self.user))
        self.assertTrue(company.status(self.user)['configured'])
        self.post({'api_key': '', 'model': 'grok-other', 'enabled': True})
        self.assertEqual(company.credentials(self.user)['api_key'], CONFIG['api_key'])

    def test_bad_input_and_busy_preserve_existing_connection_over_http(self):
        self.post({**CONFIG, 'enabled': True})
        original = company.path(self.user).read_bytes()
        for bad in [{'endpoint': 'https://evil.test'}, {'api_key': 'bad\nkey'}, {'model': ''}, {'enabled': 'yes'}]:
            self.assertEqual(self.post({**CONFIG, 'enabled': True, **bad}).status_code, 400)
        Job.objects.create(owner=self.user, mode='codex', title='busy')
        self.assertEqual(self.post({**CONFIG, 'enabled': False}).status_code, 400)
        self.assertEqual(company.path(self.user).read_bytes(), original)

    def test_explicit_probe_uses_synthetic_image_and_failed_probe_clears_verification(self):
        self.post({**CONFIG, 'enabled': True})
        def inspect(config, prompt, files, schema, **kwargs):
            self.assertEqual(len(files), 1)
            with Image.open(files[0]) as image:
                self.assertEqual(image.size, (32, 32))
                return {'color': { (255, 0, 0): 'red', (0, 255, 0): 'green', (0, 0, 255): 'blue'}[image.getpixel((0, 0))]}
        with patch('company_agent.analyze', side_effect=inspect) as call:
            result = self.post({}, 'test')
            self.assertEqual(result.status_code, 200, result.content)
            self.assertTrue(result.json()['verified'])
            call.assert_called_once()
        with patch('company_agent.analyze', side_effect=agent.CompanyError('公司 Agent 测试失败')):
            self.assertEqual(self.post({}, 'test').status_code, 400)
        self.assertFalse(company.status(self.user)['verified'])

    def test_selection_prefers_configured_codex_and_does_not_fall_back_on_failure(self):
        from shijie.pipeline import ai
        self.assertEqual(ai.selected_provider(self.user), 'codex')
        self.post({**CONFIG, 'enabled': True})
        self.assertEqual(ai.selected_provider(self.user), 'company')
        ai.home(self.user).mkdir()
        (ai.home(self.user) / 'auth.json').write_text('{"test":"configured"}')
        self.assertEqual(ai.selected_provider(self.user), 'codex')
        from .test_service import png
        with patch('shijie.pipeline.ai.status', return_value={'ok': False}) as status:
            response = self.client.post('/api/engine/jobs', json.dumps({'image': png()}), content_type='application/json')
        self.assertEqual(response.status_code, 503)
        status.assert_called_once()
        self.assertFalse(Job.objects.exists())

    def test_company_only_generation_queues_with_company_without_starting_codex(self):
        from .test_service import png
        self.post({**CONFIG, 'enabled': True})
        with patch('shijie.pipeline.ai.status') as codex:
            response = self.client.post('/api/engine/jobs', json.dumps({'image': png()}), content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        codex.assert_not_called()
        from shijie.pipeline.storage import job_root
        self.assertEqual(json.loads((job_root(Job.objects.get()) / 'connection.json').read_text()), {'provider': 'company', 'analysisProvider':'company', 'imageProvider':'codex', 'needsCodex':False,'codexModel':self.user.codex_model})

    def test_company_only_analysis_can_queue_without_codex(self):
        from .test_service import png
        from shijie.pipeline.storage import job_root
        self.post({**CONFIG, 'enabled': True})
        scene = {'format': 'shijie-scene', 'version': 2, 'width': 4, 'height': 3,
                 'source': png(), 'nodes': [{'id': 'a', 'type': 'rect', 'x': 0, 'y': 0, 'width': 4, 'height': 3, 'fill': '#ff0000'}]}
        with patch('shijie.pipeline.ai.status') as codex:
            response = self.client.post('/api/engine/jobs', json.dumps({'image': png(), 'mode': 'repair-order', 'resume': scene}), content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        codex.assert_not_called()
        job = Job.objects.get()
        self.assertEqual(json.loads((job_root(job) / 'connection.json').read_text()), {'provider': 'company', 'analysisProvider':'company', 'imageProvider':'codex', 'needsCodex':False,'codexModel':self.user.codex_model})

    def test_http_credentials_require_csrf_login_and_permission(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        routes = ('company/connection', 'company/test', 'codex/api-key', 'codex/access-token', 'assistant/key', 'image-provider')
        for route in routes:
            self.assertEqual(client.post('/api/engine/' + route, '{}', content_type='application/json').status_code, 403)
            self.assertEqual(Client().post('/api/engine/' + route, '{}', content_type='application/json').status_code, 401)
        self.assertFalse(company.path(self.user).exists())
        csrf = client.get('/api/me').json()['csrf']
        response = client.post('/api/engine/company/connection', json.dumps({**CONFIG, 'enabled': True}),
                               content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN='http://testserver')
        self.assertEqual(response.status_code, 200, response.content)
        original = company.path(self.user).read_bytes()
        response = client.post('/api/engine/company/connection', json.dumps({**CONFIG, 'enabled': False}),
                               content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN='http://foreign.example')
        self.assertEqual(response.status_code, 403)
        self.user.groups.clear()
        for route in routes:
            self.assertEqual(client.post('/api/engine/' + route, '{}', content_type='application/json', HTTP_X_CSRFTOKEN=csrf).status_code, 403)
        self.assertEqual(company.path(self.user).read_bytes(), original)

    def test_company_status_never_starts_an_unconfigured_codex_process(self):
        from shijie.pipeline import ai
        self.post({**CONFIG, 'enabled': True})
        with patch('shijie.pipeline.ai.execute') as execute:
            state = ai.connections(self.user)
        execute.assert_not_called()
        self.assertEqual(state['active'], 'company')
        self.assertFalse(state['codex']['configured'])
        self.assertNotIn(CONFIG['api_key'], json.dumps(state))

    def test_job_credentials_travel_only_over_stdin_and_are_bounded(self):
        from shijie.pipeline.processes import start
        from shijie.pipeline.storage import user_root
        root = user_root(self.user.pk) / 'transport-test'
        with patch('shijie.pipeline.processes.subprocess.Popen') as popen:
            process = start('run_job.py', root, root / 'codex', 'job', '', input_data=CONFIG)
            args, kwargs = popen.call_args
            self.assertNotIn(CONFIG['api_key'], str(args) + str(kwargs['env']))
            self.assertEqual(json.loads(process.stdin.write.call_args.args[0]), CONFIG)
            process.stdin.close.assert_called_once()
            self.assertEqual(list(root.glob('*.json')), [])
            popen.reset_mock()
            with self.assertRaises(ValueError): start('run_job.py', root, root / 'codex', input_data={'key': 'x' * 17000})
            popen.assert_not_called()
