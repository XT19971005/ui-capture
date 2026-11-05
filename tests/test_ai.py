import fcntl
import json
import subprocess
import tempfile
import threading
import time
import requests
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from shijie.accounts.models import User
from shijie.pipeline import ai
from shijie.pipeline.models import Job
from shijie.pipeline.storage import write_json


class Connections(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        override = override_settings(DATA_ROOT=Path(tmp.name))
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user(username='connect')
        self.user.groups.add(Group.objects.get_or_create(name='使用者')[0])
        self.client.force_login(self.user)
        self.home = ai.home(self.user)
        self.home.mkdir(mode=0o700)

    def post(self, route, value):
        return self.client.post('/api/engine/codex/' + route, json.dumps(value), content_type='application/json', HTTP_HOST='testserver')

    def pending(self):
        ident = 'a0f9213b-65a8-43cd-8aba-c03bb45e49eb'
        root = self.home.parent / 'ai-requests' / ident
        root.mkdir(parents=True)
        value = {'requestId': ident, 'url': 'https://auth.openai.com/codex/device',
                 'userCode': 'TEST-1234', 'expiresAt': time.time() + 600}
        write_json(self.home / 'device-login.json', value)
        lock = (self.home / 'account.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(lock.close)
        return root, lock

    def test_reopening_and_repeated_login_keep_current_code_without_new_process(self):
        self.pending()
        with patch('shijie.pipeline.ai.start') as start:
            response = self.post('login', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['userCode'], 'TEST-1234')
        start.assert_not_called()
        state = self.client.get('/api/engine/codex/login').json()
        self.assertEqual(state['pending']['userCode'], 'TEST-1234')
        self.assertNotIn('requestId', state['pending'])

    def test_cancel_releases_pending_login_without_touching_existing_credentials(self):
        root, lock = self.pending()
        (self.home / 'auth.json').write_text('existing-account')
        def finish():
            for _ in range(100):
                if (root / 'cancel').exists():
                    (self.home / 'device-login.json').unlink()
                    lock.close()
                    return
                time.sleep(.02)
        worker = threading.Thread(target=finish)
        worker.start()
        try:
            response = self.post('login/cancel', {})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['ok'])
            self.assertTrue((root / 'cancel').exists())
            self.assertEqual((self.home / 'auth.json').read_text(), 'existing-account')
        finally:
            worker.join()

    def test_access_token_is_stdin_only_committed_after_verification(self):
        token = 'test-token-private-value-12345'
        def cli(argv, **kwargs):
            self.assertIn('--with-access-token', argv)
            self.assertNotIn(token, str(argv) + str(kwargs['env']))
            self.assertEqual(kwargs['input'], token)
            staged = Path(kwargs['env']['CODEX_HOME'])
            self.assertNotEqual(staged, self.home)
            write_json(staged / 'auth.json', {'auth_mode': 'personalAccessToken', 'test': 'credential'})
            return subprocess.CompletedProcess(argv, 0)
        with patch('subprocess.run', side_effect=cli), patch('shijie.pipeline.ai.execute', return_value={'ok': True, 'ready': True, 'imageGeneration': True, 'models': [], 'plan': 'business'}):
            response = self.post('access-token', {'token': token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ready'])
        self.assertNotIn(token, response.content.decode())
        self.assertEqual((self.home / 'auth.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.home.glob('token-check-*')))

    def test_invalid_failed_and_busy_token_attempts_preserve_existing_account(self):
        (self.home / 'auth.json').write_text('existing-account')
        with patch('subprocess.run') as run:
            for token in ['', 'x' * 9000, 'unsafe\nvalue', {'token': 'x'}]:
                self.assertEqual(self.post('access-token', {'token': token}).status_code, 400)
            run.assert_not_called()
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            response = self.post('access-token', {'token': 'rejected-private-token-value'})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('rejected-private', response.content.decode())
        Job.objects.create(owner=self.user, mode='codex', title='busy')
        with patch('subprocess.run') as run:
            self.assertEqual(self.post('access-token', {'token': 'busy-private-token-value'}).status_code, 400)
            run.assert_not_called()
        self.assertEqual((self.home / 'auth.json').read_text(), 'existing-account')

    def test_unverified_staged_account_does_not_replace_existing_credentials(self):
        (self.home / 'auth.json').write_text('existing-account')
        def cli(argv, **kwargs):
            write_json(Path(kwargs['env']['CODEX_HOME']) / 'auth.json', {'test': 'new-unverified-account'})
            return subprocess.CompletedProcess(argv, 0)
        with patch('subprocess.run', side_effect=cli), patch('shijie.pipeline.ai.execute', return_value={'ok': False, 'ready': False}):
            response = self.post('access-token', {'token': 'private-token-verify-failed'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.home / 'auth.json').read_text(), 'existing-account')
        self.assertFalse(list(self.home.glob('token-check-*')))

    def test_http_token_endpoint_still_requires_csrf(self):
        from django.test import Client
        with patch('subprocess.run') as run:
            browser = Client(enforce_csrf_checks=True)
            browser.force_login(self.user)
            response = browser.post('/api/engine/codex/access-token', '{"token":"private-token-123456789"}', content_type='application/json')
            self.assertEqual(response.status_code, 403)
            run.assert_not_called()

    def test_api_key_uses_its_own_authentication_and_never_leaks(self):
        key = 'sk-proj-private-platform-test-key'
        def cli(argv, **kwargs):
            self.assertIn('--with-api-key', argv)
            self.assertNotIn('--with-access-token', argv)
            self.assertNotIn(key, str(argv) + str(kwargs['env']))
            self.assertEqual(kwargs['input'], key)
            write_json(Path(kwargs['env']['CODEX_HOME']) / 'auth.json', {'auth_mode':'apikey', 'OPENAI_API_KEY':key})
            return subprocess.CompletedProcess(argv, 0)
        with patch('shijie.pipeline.ai.verify_api_key', create=True) as verify, patch('subprocess.run', side_effect=cli), patch('shijie.pipeline.ai.execute', return_value={'ok':True, 'ready':True, 'provider':'apiKey', 'imageGeneration':True}):
            response = self.post('api-key', {'api_key':key})
        self.assertEqual(response.status_code, 200)
        verify.assert_called_once_with(key)
        self.assertEqual(response.json()['provider'], 'apiKey')
        self.assertNotIn(key, response.content.decode())
        self.assertEqual((self.home / 'auth.json').stat().st_mode & 0o777, 0o600)

    def test_rejected_api_key_preserves_existing_account_and_never_runs_cli(self):
        (self.home / 'auth.json').write_text('existing-account')
        with patch('shijie.pipeline.ai.verify_api_key', create=True, side_effect=ValueError('OpenAI API Key 无效')) as verify, patch('subprocess.run') as cli:
            response = self.post('api-key', {'api_key':'sk-proj-rejected-test-key'})
        self.assertEqual(response.status_code, 400)
        verify.assert_called_once()
        cli.assert_not_called()
        self.assertEqual((self.home / 'auth.json').read_text(), 'existing-account')

    def test_api_key_boundary_checks_and_failed_verification_leave_existing_account(self):
        from django.test import Client
        (self.home / 'auth.json').write_text('existing-account')
        with patch('shijie.pipeline.ai.verify_api_key', create=True) as verify, patch('subprocess.run') as cli:
            for key in ['', 'x'*9000, 'unsafe\nkey', {'key':'x'}]:
                self.assertEqual(self.post('api-key', {'api_key':key}).status_code, 400)
            payload = {'api_key':'sk-proj-private-platform-test-key'}
            browser = Client(enforce_csrf_checks=True); browser.force_login(self.user)
            self.assertEqual(browser.post('/api/engine/codex/api-key', json.dumps(payload), content_type='application/json').status_code, 403)
            Job.objects.create(owner=self.user, mode='codex', title='busy')
            self.assertEqual(self.post('api-key', payload).status_code, 400)
            verify.assert_not_called(); cli.assert_not_called()
        self.assertEqual((self.home / 'auth.json').read_text(), 'existing-account')

    def test_key_expired_after_save_reports_not_ready_without_falling_back(self):
        write_json(self.home / 'auth.json', {'auth_mode':'apikey', 'OPENAI_API_KEY':'sk-proj-private-expired-key'})
        with patch('shijie.pipeline.ai.verify_api_key', create=True, side_effect=ValueError('OpenAI API Key 已失效')), patch('shijie.pipeline.ai.execute') as execute:
            state = ai.status(self.user)
        self.assertFalse(state['ready'])
        self.assertIn('已失效', state['error'])
        self.assertNotIn('sk-proj-', json.dumps(state))
        execute.assert_not_called()
        self.assertEqual(ai.selected_provider(self.user), 'codex')


class ApiKeyVerification(TestCase):
    def test_authentication_uses_official_endpoint_once_and_hides_upstream_text(self):
        from unittest.mock import MagicMock
        for code in (200, 401, 403, 429, 500, 302):
            session = MagicMock(); response = session.get.return_value.__enter__.return_value
            response.status_code = code
            response.text = 'upstream private-platform-test-key'
            with self.subTest(status=code), patch('shijie.pipeline.ai.requests.Session', create=True) as factory:
                factory.return_value.__enter__.return_value = session
                if code == 200: ai.verify_api_key('private-platform-test-key')
                else:
                    with self.assertRaises(ValueError) as error: ai.verify_api_key('private-platform-test-key')
                    self.assertNotIn('private-platform-test-key', str(error.exception))
                    self.assertIn(str(code), str(error.exception))
            session.get.assert_called_once_with('https://api.openai.com/v1/models', headers={'Authorization':'Bearer private-platform-test-key'}, stream=True, timeout=(10, 20), allow_redirects=False)
            self.assertFalse(session.trust_env)

    def test_network_failure_is_safe_and_not_retried(self):
        with patch('shijie.pipeline.ai.requests.Session', create=True) as factory:
            client = factory.return_value.__enter__.return_value
            client.get.side_effect = requests.RequestException('private-platform-test-key')
            with self.assertRaises(ValueError) as error: ai.verify_api_key('private-platform-test-key')
        self.assertNotIn('private-platform-test-key', str(error.exception))
        self.assertIn('网络', str(error.exception))
        client.get.assert_called_once()
