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
                job=Job.objects.create(owner=self.user,mode='codex',title='timeout',cancel_requested=user_cancelled)
                root=job_root(job);write_scene(root/'partial.json',{'nodes':[{'id':'kept'}]})
                # The child reacts to the worker's cancel file with a normal cancellation receipt.
                (root/'finished.json').write_text(json.dumps({'status':'cancelled','message':'已取消，中间图层已保留'}))
                process=Mock();process.poll.side_effect=[None,0]
                clock=Mock();clock.monotonic.side_effect=[0,46]
                with patch('shijie.pipeline.worker.start',return_value=process),patch('shijie.pipeline.worker.stop'),patch('shijie.pipeline.worker.time',clock):
                    run(claim())
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
