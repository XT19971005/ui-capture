import json
import os
import tempfile
import subprocess
import base64
from pathlib import Path
from unittest.mock import patch, Mock
from django.contrib.auth.models import Group
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from shijie.accounts.models import User
from shijie.pipeline import ai
from shijie.pipeline.models import Job
from shijie.pipeline.processes import environment
from shijie.pipeline.storage import job_root, read_scene, write_scene
from shijie.pipeline.worker import claim, recover, run
from .test_service import png


class Queue(TransactionTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.override = override_settings(DATA_ROOT=Path(self.temp.name), JOB_TIMEOUT=45)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = User.objects.create_user(username='worker', email='worker@example.test')
        self.user.groups.add(Group.objects.get_or_create(name='使用者')[0])

    def test_claim_once_and_interrupted_job_keeps_partial_without_replay(self):
        first = Job.objects.create(owner=self.user, mode='codex', title='first')
        second = Job.objects.create(owner=self.user, mode='codex', title='second')
        self.assertEqual(claim().pk, first.pk)
        self.assertEqual(claim().pk, second.pk)
        self.assertIsNone(claim())
        write_scene(job_root(first) / 'partial.json', {'nodes': [{'id': 'kept'}]})
        self.assertEqual(recover(), 2)
        first.refresh_from_db()
        self.assertEqual(first.status, 'failed')
        self.assertIsNone(claim())
        self.assertEqual(read_scene(job_root(first) / 'partial.json')['nodes'], [{'id': 'kept'}])

    def test_timeout_is_not_reported_as_user_cancellation_and_keeps_partial(self):
        for user_cancelled in (False, True):
            with self.subTest(user_cancelled=user_cancelled):
                job=Job.objects.create(owner=self.user,mode='codex',title='timeout')
                claimed=claim()
                if user_cancelled:Job.objects.filter(pk=job.pk).update(cancel_requested=True)
                root=job_root(job);write_scene(root/'partial.json',{'nodes':[{'id':'kept'}]})
                # The child reacts to the worker's cancel file with a normal cancellation receipt.
                (root/'finished.json').write_text(json.dumps({'status':'cancelled','message':'已取消，中间图层已保留'}))
                process=Mock();process.poll.side_effect=[None,0]
                clock=Mock();clock.monotonic.side_effect=[0,46]
                with patch('shijie.pipeline.worker.start',return_value=process),patch('shijie.pipeline.worker.stop'),patch('shijie.pipeline.worker.time',clock):
                    run(claimed)
                job.refresh_from_db()
                self.assertEqual(job.status,'cancelled' if user_cancelled else 'failed')
                self.assertIn('已取消' if user_cancelled else '任务超时',job.message)
                self.assertEqual(read_scene(root/'partial.json')['nodes'],[{'id':'kept'}])
                self.assertEqual(json.loads((root/'finished.json').read_text())['status'],job.status)

    def test_child_environment_contains_only_explicit_user_credentials_location(self):
        with patch.dict(os.environ, {'SHIJIE_DATABASE_URL': 'private-db', 'OPENAI_API_KEY': 'private-key', 'CODEX_HOME': '/private-developer-home'}):
            env = environment(Path('/task'), Path('/personal-ai'))
        self.assertEqual(env['CODEX_HOME'], '/personal-ai')
        self.assertNotIn('SHIJIE_DATABASE_URL', env)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('SHIJIE_CONFIG', env)

    def test_real_runner_with_invalid_input_fails_and_retains_recovery(self):
        job = Job.objects.create(owner=self.user, mode='codex', title='invalid')
        write_scene(job_root(job) / 'input.json', {'image': 'data:image/png;base64,aW52YWxpZA=='})
        write_scene(job_root(job) / 'partial.json', {'nodes': [{'id': 'previous'}]})
        run(claim())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertEqual(read_scene(job_root(job) / 'partial.json')['nodes'][0]['id'], 'previous')
        self.assertFalse((job_root(job) / 'result.json').exists())
        diagnostic = json.loads((job_root(job) / 'failure.json').read_text())
        self.assertEqual(diagnostic['exception'], 'ValueError')
        self.assertEqual(diagnostic['stage'], 'validate_input')
        self.assertTrue(diagnostic['frames'])
        self.assertNotIn('message', diagnostic)
        self.assertNotIn('aW52YWxpZA==', json.dumps(diagnostic))

    def test_real_codex_status_uses_empty_personal_home(self):
        state = ai.status(self.user)
        self.assertTrue(state['ok'], state)
        self.assertFalse(state['ready'])
        self.assertEqual(state['models'], [])
        self.assertNotEqual(ai.home(self.user), ai.home(User(pk=self.user.pk + 1)))

    def test_runner_reports_missing_account_and_preserves_input(self):
        job = Job.objects.create(owner=self.user, mode='codex', title='no-account')
        write_scene(job_root(job) / 'input.json', {'image': png()})
        run(claim())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        self.assertIn('当前账号尚未连接 Codex', job.message)
        self.assertIn('连接 Codex', job.message)
        self.assertEqual(read_scene(job_root(job) / 'input.json')['image'], png())
        self.assertFalse((job_root(job) / 'result.json').exists())

    def test_linux_text_fitting_uses_installed_fonts(self):
        request = {'text': 'Hello 世界', 'width': 90, 'height': 30,
                   'mask': base64.b64encode(b'\1' * 2700).decode()}
        result = subprocess.run(['node', str(settings.ENGINE_ROOT / 'text_candidates.cjs')],
                                input=json.dumps(request), text=True, capture_output=True, check=True, timeout=30,
                                env=environment(Path(self.temp.name), Path(self.temp.name) / 'codex'))
        candidates = json.loads(result.stdout)['candidates']
        self.assertTrue(candidates)
        self.assertEqual({c['family'] for c in candidates}, {'Noto Sans CJK SC'})

    def test_company_job_is_independent_of_pending_codex_login(self):
        import fcntl
        from shijie.pipeline import company
        company.save(self.user, {'api_key': 'private-test-company-key', 'model': 'grok-4.6', 'enabled': True})
        job = Job.objects.create(owner=self.user, mode='codex', title='company-no-codex')
        write_scene(job_root(job) / 'input.json', {'image': 'data:image/png;base64,aW52YWxpZA=='})
        ai.home(self.user).mkdir()
        with (ai.home(self.user) / 'account.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(claim())
        job.refresh_from_db()
        self.assertEqual(job.status, 'failed')
        diagnostic = json.loads((job_root(job) / 'failure.json').read_text())
        self.assertEqual(diagnostic['exception'], 'ValueError')
        self.assertEqual(diagnostic['stage'], 'validate_input')
        self.assertNotIn('private-test-company-key', json.dumps(diagnostic))


class DesktopDelivery(TransactionTestCase):
    """Real relay/worker round trips with a fake transport and disposable storage."""
    def setUp(self):
        import hashlib
        import sys
        from django.test import Client
        from django.utils import timezone
        from shijie.pipeline.models import DesktopService
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.override = override_settings(DATA_ROOT=self.root / 'server', MIN_FREE=1, LAN_SHARED=True)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.path = patch.object(sys, 'path', [str(settings.BASE_DIR / 'tools'), *sys.path])
        self.path.start(); self.addCleanup(self.path.stop)
        import desktop_worker
        self.worker_module = desktop_worker
        self.worker = desktop_worker.DesktopWorker({'url':'http://127.0.0.1:19218', 'token':'fake-token-' * 5}, self.root / 'worker')
        self.token = self.worker.token
        self.service = DesktopService.objects.create(pk=1, enabled=True,
            token_digest=hashlib.sha256(self.token.encode()).hexdigest(), heartbeat=timezone.now(),
            capabilities={'ready':True,'models':[{'id':'fake-model','name':'Fake'}],'model':'fake-model','imageGeneration':True})
        self.clients = []
        for name in ('first-delivery', 'second-delivery'):
            user = User.objects.create_user(username=name, email=name+'@example.test')
            user.groups.add(Group.objects.get_or_create(name='使用者')[0])
            client = Client(); client.force_login(user); self.clients.append(client)
        self.relay_client = Client()
        self.worker.remote = self.remote

    def relay(self, action, value, token=None):
        from local_project_store import pack_record
        return self.relay_client.post('/desktop-relay/v1/'+action, pack_record(value),
            content_type='application/json', HTTP_AUTHORIZATION='Bearer '+(token or self.token))

    def remote(self, action, value):
        from image_wire import decode_job
        response = self.relay(action, value)
        if response.status_code != 200:
            raise RuntimeError('fake transport HTTP '+str(response.status_code))
        return decode_job(response.json())

    def pending_job(self):
        from uuid import uuid4
        for client in self.clients:
            response = client.post('/api/engine/jobs', {'image':png(),'title':'待回传样例'}, content_type='application/json')
            self.assertEqual(response.status_code, 202, response.content)
        job = self.remote('claim', {})['job']; job['run'] = str(uuid4())
        self.assertTrue(self.remote('start', {key:job[key] for key in ('id','lease','run')})['execute'])
        folder = self.worker.state / 'jobs' / job['id']
        self.worker_module.atomic_json(folder/'receipt.json', {'lease':job['lease'],'run':job['run'],'started':True})
        self.worker_module.atomic_json(folder/'finished.json', {'status':'completed','elapsedSeconds':1})
        self.worker_module.atomic_json(folder/'result.json', {'format':'shijie-scene','version':2,'title':'已生成',
            'width':4,'height':3,'source':png(),'nodes':[],'groups':[],'edges':[]})
        return job, folder

    def test_full_owner_quota_releases_other_users_queue_then_delivers_without_execution(self):
        job, folder = self.pending_job()
        saved_partial = {'format':'shijie-scene','version':2,'title':'已有图层','width':4,'height':3,
                         'source':png(),'nodes':[],'groups':[],'edges':[]}
        write_scene(job_root(Job.objects.get(pk=job['id']))/'partial.json', saved_partial)
        with patch.object(self.worker_module.DesktopWorker, 'launch', side_effect=AssertionError('must never replay generation')):
            with override_settings(USER_QUOTA=1):
                self.worker.recover_outbox()
                pending = Job.objects.get(pk=job['id'])
                self.assertEqual(pending.status, 'delivery-pending')
                visible = self.clients[0].get('/api/engine/jobs/'+job['id']).json()
                self.assertEqual(visible['status'], 'failed')
                self.assertTrue(visible['deliveryPending'])
                self.assertIn('等待回传', visible['message'])
                self.assertEqual(visible['partial']['title'], '已有图层')
                self.assertTrue((folder/'result.json').exists())
                second = self.remote('claim', {})['job']
                self.assertNotEqual(second['id'], job['id'])
            # A fresh worker recovers only the durable receipt, never model execution.
            self.worker = self.worker_module.DesktopWorker({'url':'http://127.0.0.1:19218','token':self.token}, self.worker.state)
            self.worker.remote = self.remote
            after_retry = self.worker_module.time.time()+61
            with patch.object(self.worker_module.time, 'time', return_value=after_retry):
                self.worker.recover_outbox()
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.assertFalse(folder.exists())
        self.assertEqual(read_scene(job_root(pending)/'result.json')['title'], '已生成')

    def test_defer_requires_pair_token_lease_and_run_and_pending_purge_is_owner_only(self):
        job, folder = self.pending_job()
        permit = {**{key:job[key] for key in ('id','lease','run')}, 'status':'delivery-pending'}
        self.assertEqual(self.relay('update', permit, 'wrong-token-'*5).status_code, 401)
        for field, invalid in (('lease','incorrect'),('run','00000000-0000-0000-0000-000000000000')):
            self.assertEqual(self.relay('update', {**permit,field:invalid}).status_code, 409)
        self.assertEqual(self.relay('update', {**permit,'result':{}}).status_code, 400)
        self.assertTrue(self.remote('update', permit)['deferred'])
        import hashlib
        psd = b'8BPS\x00\x01'+b'\0'*20
        artifact = self.relay_client.generic('POST', '/desktop-relay/v1/artifact', psd,
            content_type='application/octet-stream', HTTP_AUTHORIZATION='Bearer '+self.token,
            HTTP_X_SHIJIE_JOB=job['id'], HTTP_X_SHIJIE_LEASE=job['lease'], HTTP_X_SHIJIE_RUN=job['run'],
            HTTP_X_CONTENT_SHA256=hashlib.sha256(psd).hexdigest())
        self.assertEqual(artifact.status_code, 200, artifact.content)
        self.assertEqual((job_root(Job.objects.get(pk=job['id']))/'result.psd').read_bytes(), psd)
        cleanup = self.clients[0].delete('/api/engine/jobs/'+job['id']).json()
        self.assertTrue(cleanup['deliveryPending'])
        self.assertEqual(Job.objects.get(pk=job['id']).status, 'delivery-pending')
        self.assertEqual(self.clients[1].post('/api/engine/jobs/'+job['id']+'/purge', {}, content_type='application/json').status_code, 404)
        self.assertEqual(self.clients[0].post('/api/engine/jobs/'+job['id']+'/purge', {}, content_type='application/json').status_code, 200)
        with patch.object(self.worker, 'launch', side_effect=AssertionError('must never replay generation')):
            self.worker.recover_outbox()
        self.assertFalse(folder.exists())

    def test_failed_defer_keeps_running_slot_and_stops_new_claims(self):
        job, folder = self.pending_job()
        self.worker.capabilities = self.service.capabilities
        self.worker.last_probe = self.worker_module.time.monotonic()
        def disconnected_defer(action, data):
            if action=='update' and data.get('status')=='delivery-pending':
                raise RuntimeError('fake unconfirmed defer')
            return self.remote(action, data)
        with override_settings(USER_QUOTA=1), patch.object(self.worker, 'remote', side_effect=disconnected_defer), \
             patch.object(self.worker_module.time, 'sleep', side_effect=StopIteration), \
             patch.object(self.worker, 'launch', side_effect=AssertionError('must never replay generation')):
            with self.assertRaises(StopIteration): self.worker.run()
        self.assertEqual(Job.objects.get(pk=job['id']).status, 'running')
        self.assertEqual(Job.objects.filter(status='queued').count(), 1)
        self.assertTrue((folder/'result.json').exists())
        self.assertFalse(json.loads((self.worker.state/'status.json').read_text())['connected'])

    def test_old_receipt_without_run_is_preserved_when_delivery_cannot_be_deferred(self):
        job, folder = self.pending_job()
        with self.assertRaisesMessage(RuntimeError, '保留本机结果'):
            self.worker.defer_delivery(folder, {key:job[key] for key in ('id','lease')})
        self.assertTrue((folder/'result.json').exists())
        self.assertEqual(Job.objects.get(pk=job['id']).status, 'running')

    def test_recovery_attempts_one_due_result_and_prioritizes_untried_receipts(self):
        from uuid import uuid4
        first, folder = self.pending_job()
        with override_settings(USER_QUOTA=1): self.worker.recover_outbox()
        first_retry = json.loads((folder/'receipt.json').read_text())['retryAfter']
        second = self.remote('claim', {})['job']; second['run'] = str(uuid4())
        self.assertTrue(self.remote('start', {key:second[key] for key in ('id','lease','run')})['execute'])
        second_folder = self.worker.state/'jobs'/second['id']
        self.worker_module.atomic_json(second_folder/'receipt.json', {'lease':second['lease'],'run':second['run'],'started':True})
        self.worker_module.atomic_json(second_folder/'finished.json', {'status':'completed','elapsedSeconds':1})
        self.worker_module.atomic_json(second_folder/'result.json', json.loads((folder/'result.json').read_text()))
        after_retry = first_retry+1
        with override_settings(USER_QUOTA=1), patch.object(self.worker_module.time, 'time', return_value=after_retry), \
             patch.object(self.worker, 'launch', side_effect=AssertionError('must never replay generation')):
            self.worker.recover_outbox()
        self.assertEqual(json.loads((folder/'receipt.json').read_text())['retryAfter'], first_retry)
        self.assertGreater(json.loads((second_folder/'receipt.json').read_text())['retryAfter'], first_retry)
        self.assertEqual(Job.objects.get(pk=second['id']).status, 'delivery-pending')

    def test_lan_restart_preserves_pause_but_first_launch_enables_service(self):
        from contextlib import ExitStack
        import lan_server
        from shijie.pipeline.models import DesktopService
        state = self.root / 'lan'
        state.mkdir(); (state/'site.json').write_text('{}')
        worker_state = state / 'worker'; worker_state.mkdir()
        (worker_state/'connection.dat').write_text(json.dumps({'url':'http://127.0.0.1:19218','token':self.token}))
        for existing in (False, True, None):
            with self.subTest(existing=existing), ExitStack() as stack:
                if existing is None: DesktopService.objects.all().delete()
                else: DesktopService.objects.filter(pk=1).update(enabled=existing)
                server = Mock(); process = Mock(); process.poll.return_value = 1
                stack.enter_context(override_settings(LAN_CONFIG={'host':'172.16.8.2'}))
                for name, value in [('STATE',state),('private_directory',lambda path:None),('environment',lambda:None),
                                    ('protect',lambda raw,**kwargs:raw),('configure',Mock()),('DesktopWorker',Mock()),
                                    ('ProcessTree',Mock())]:
                    stack.enter_context(patch.object(lan_server,name,value))
                stack.enter_context(patch('django.core.management.call_command'))
                stack.enter_context(patch('waitress.server.create_server',return_value=server))
                stack.enter_context(patch.object(lan_server.threading,'Thread'))
                stack.enter_context(patch.object(lan_server.subprocess,'Popen',return_value=process))
                with self.assertRaisesMessage(ValueError, '本机接单程序已停止'):
                    lan_server.run()
                self.assertEqual(DesktopService.objects.get(pk=1).enabled, True if existing is None else existing)
