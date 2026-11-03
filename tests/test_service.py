import base64
import io
import tempfile
from unittest.mock import patch
from pathlib import Path
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from shijie.accounts.models import User
from shijie.accounts.services import grant
from shijie.pipeline.models import Job
from PIL import Image


def png():
    out = io.BytesIO()
    Image.new('RGB', (4, 3), '#ff0000').save(out, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


class Service(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = override_settings(DATA_ROOT=Path(self.folder.name), MIN_FREE=1)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.a = User.objects.create_user(username='a', email='a@example.test')
        self.b = User.objects.create_user(username='b', email='b@example.test')
        for u in (self.a, self.b):
            u.groups.add(Group.objects.get_or_create(name='使用者')[0])
        self.client.force_login(self.a)
        self.other = Client()
        self.other.force_login(self.b)
        self.record = {'id': 'example', 'title': '原图', 'kind': 'image', 'saveMode': 'saved',
                       'doc': {'_projectId': 'example', 'width': 4, 'height': 3, 'source': png(), 'nodes': []}}

    def send(self, route, data, method='post', client=None):
        return getattr(client or self.client, method)('/api/engine/' + route, data, content_type='application/json')

    def test_private_project_roundtrip_and_stale_save(self):
        first = self.send('saved-projects/example', self.record, 'put')
        self.assertEqual(first.status_code, 200, first.content)
        version = first.json()['project']['persistedVersion']
        self.assertEqual(self.other.get('/api/engine/saved-projects').json()['projects'], [])
        self.assertEqual(self.other.get('/api/engine/saved-projects/example').status_code, 404)
        self.assertEqual(self.send('saved-projects/example', self.record, 'put').status_code, 409)
        updated = {**self.record, 'title': '改名', '_expectedVersion': version}
        self.assertEqual(self.send('saved-projects/example', updated, 'put').status_code, 200)
        self.assertEqual(self.send('saved-projects/example', {'_expectedVersion': version}, 'delete').status_code, 409)
        self.assertEqual(self.client.get('/api/engine/saved-projects').json()['projects'][0]['title'], '改名')

    def test_csrf_revocation_and_changed_browser_identity(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.a)
        self.assertEqual(self.send('saved-projects/example', self.record, 'put', c).status_code, 403)
        self.assertEqual(self.client.get('/api/me', HTTP_X_SHIJIE_USER=str(self.b.pk)).status_code, 409)
        self.a.groups.clear()
        self.assertEqual(self.client.get('/api/engine/saved-projects').status_code, 403)

    def test_job_validation_isolation_cancel_and_persistence(self):
        self.assertEqual(self.send('jobs', {'image': 'data:image/png;base64,bm90IGEgcG5n'}).status_code, 400)
        self.assertEqual(self.send('jobs', {'image': png(), 'mode': '../file'}).status_code, 400)
        with patch('shijie.pipeline.ai.status', return_value={'ok': True, 'ready': True, 'imageGeneration': True}):
            response = self.send('jobs', {'image': png(), 'title': '样例'})
        self.assertEqual(response.status_code, 202, response.content)
        ident = response.json()['id']
        self.assertTrue(Job.objects.filter(pk=ident, owner=self.a, status='queued').exists())
        self.assertTrue(list(Path(self.folder.name).rglob('input.json')))
        restored = self.client.get('/api/engine/jobs/' + ident).json()['input']
        self.assertEqual(restored['source'], png())
        self.assertEqual((restored['width'], restored['height']), (4, 3))
        self.assertEqual(self.send('jobs/' + ident + '/purge', {}).status_code, 409)
        self.assertEqual(self.other.get('/api/engine/jobs/' + ident).status_code, 404)
        self.assertEqual(self.send('jobs/' + ident, {}, 'delete', self.other).status_code, 404)
        self.assertEqual(self.send('jobs/' + ident, {}, 'delete').status_code, 200)
        self.assertEqual(self.client.get('/api/engine/jobs/' + ident).json()['status'], 'cancelled')
        self.assertEqual(self.send('jobs/' + ident + '/purge', {}, client=self.other).status_code, 404)
        self.assertEqual(self.send('jobs/' + ident + '/purge', {}).status_code, 200)
        self.assertEqual(self.client.get('/api/engine/jobs/' + ident).status_code, 404)

    def test_job_requires_personal_codex_before_queueing(self):
        response = self.send('jobs', {'image': png(), 'title': '未连接账号'})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['code'], 'CODEX_LOGIN_REQUIRED')
        self.assertIn('连接 Codex', response.json()['error'])
        self.assertFalse(Job.objects.filter(owner=self.a).exists())
        self.assertFalse(list(Path(self.folder.name).rglob('input.json')))

    def test_unavailable_codex_or_image_generation_does_not_create_job(self):
        cases = [({'ok': False, 'error': 'provider-secret'}, 503, 'CODEX_UNAVAILABLE'),
                 ({'ok': True, 'ready': True, 'imageGeneration': False}, 422, 'CODEX_IMAGE_GENERATION_UNAVAILABLE')]
        for state, status, code in cases:
            with self.subTest(code=code), patch('shijie.pipeline.ai.status', return_value=state):
                response = self.send('jobs', {'image': png()})
                self.assertEqual(response.status_code, status, response.content)
                self.assertEqual(response.json()['code'], code)
                self.assertNotIn('provider-secret', response.content.decode())
        self.assertFalse(Job.objects.filter(owner=self.a).exists())

    def test_directory_and_path_boundaries(self):
        self.assertEqual(self.send('saved-projects/settings/location', {'directory': '/etc'}, 'put').status_code, 403)
        self.assertEqual(self.client.get('/api/engine/saved-projects/..%2Fother').status_code, 404)
        self.assertEqual(self.client.get('/../config/settings.py').status_code, 404)
        self.assertEqual(self.client.get('/image-editor.html').status_code, 200)
        self.assertEqual(self.client.get('/api/engine/connection').json()['user'], self.a.pk)

    def test_editor_serves_the_same_fonts_as_ubuntu_export(self):
        page = self.client.get('/image-editor.html').content.decode()
        self.assertIn('/static/server/fonts.css', page)
        for weight in ('Regular', 'Bold'):
            font = self.client.get(f'/static/server/fonts/NotoSansCJKsc-{weight}.woff2')
            self.assertEqual(font.status_code, 200)
            self.assertEqual(font.content[:4], b'wOF2')
            self.assertEqual(font['Content-Type'], 'font/woff2')
        self.assertEqual(self.client.get('/static/server/fonts/../../../config/settings.py').status_code, 404)

    def test_failed_save_keeps_original_project(self):
        saved = self.send('saved-projects/example', self.record, 'put').json()['project']
        changed = {**self.record, 'title': '不应写入', '_expectedVersion': saved['persistedVersion']}
        with override_settings(USER_QUOTA=1):
            self.assertEqual(self.send('saved-projects/example', changed, 'put').status_code, 507)
        with patch('local_project_store.os.replace', side_effect=OSError('disk failed')):
            self.assertEqual(self.send('saved-projects/example', changed, 'put').status_code, 507)
        from image_wire import decode_job
        project = decode_job(self.client.get('/api/engine/saved-projects/example').json()['project'])
        self.assertEqual(project['title'], self.record['title'])
        self.assertEqual(project['persistedVersion'], saved['persistedVersion'])

    def test_generated_image_paths_stay_inside_current_job_or_account(self):
        from codex_client import generated_path
        root = Path(self.folder.name).resolve()
        task, account = root / 'task', root / 'account'
        task.mkdir(); account.mkdir()
        outside = root / 'someone-else.png'
        outside.write_bytes(b'private')
        (task / 'escape.png').symlink_to(outside)
        with patch('codex_client.STATE', task), patch.dict('os.environ', {'CODEX_HOME': str(account)}):
            self.assertEqual(generated_path(task / 'result.png'), task / 'result.png')
            self.assertEqual(generated_path(account / 'images/result.webp'), account / 'images/result.webp')
            for path in (outside, task / 'escape.png', account / 'auth.json'):
                with self.assertRaises(ValueError):
                    generated_path(path)
