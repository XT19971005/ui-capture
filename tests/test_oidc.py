"""Company login and access boundaries, exercised through the HTTP views."""
import time
import base64
import hashlib
import json
import threading
from types import ModuleType
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, urlencode
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import path, include

from shijie.accounts.models import User, LoginRequest
from shijie.accounts.services import grant


BROKER = {'mode': 'broker', 'client_id': 'shijie-test',
          'login_url': 'https://company.example/authorize', 'token_url': 'https://company.example/token'}


@override_settings(OIDC=BROKER)
class LoginFlow(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', email='admin@example.test')
        self.admin.groups.add(Group.objects.get_or_create(name='超级管理员')[0])
        self.claims = {'email': 'member@example.test', 'name': '公司成员', 'issuer': '',
                       'subject': '', 'expires': int(time.time()) + 3600}

    def begin(self, client, target='/image-editor.html'):
        response = client.get('/auth/oidc/start/', {'next': target})
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlsplit(response.url).query)['state'][0]

    def finish(self, client, state):
        with patch('shijie.accounts.views.exchange', return_value=self.claims):
            return client.get('/auth/oidc/callback/', {'state': state, 'code': 'one-time-code'})

    def test_login_background_is_public_without_exposing_workspace_assets(self):
        from django.conf import settings
        response = self.client.get('/static/server/home-atmosphere.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, (settings.BASE_DIR / 'shijie/static/server/home-atmosphere.js').read_bytes())
        self.assertIn('javascript', response['Content-Type'])
        self.assertEqual(self.client.get('/static/server/home-atmosphere.js', HTTP_IF_NONE_MATCH=response['ETag']).status_code, 304)
        for protected in ('/image-editor.html', '/js/home-atmosphere.js', '/js/atmosphere.js'):
            self.assertEqual(self.client.get(protected).status_code, 302)
        self.assertEqual(self.client.get('/static/server/../templates/login.html').status_code, 404)

    def test_second_login_preserves_other_browser_session(self):
        self.finish(self.client, self.begin(self.client))
        member = User.objects.get(email=self.claims['email'])
        grant(self.admin, member, '使用者')
        self.assertEqual(self.client.get('/api/me').status_code, 200)
        other = Client()
        self.finish(other, self.begin(other))
        self.assertEqual(other.get('/api/me').status_code, 200)
        self.assertEqual(self.client.get('/api/me').status_code, 200)

    def test_pending_then_approved_returns_to_original_deep_link(self):
        target = '/index.html?project=0123456789abcdef0123456789abcdef#encode'
        self.assertEqual(self.finish(self.client, self.begin(self.client, target)).url, target)
        login_url = '/login/?' + urlencode({'next': target})
        self.assertContains(self.client.get(login_url), '等待管理员授权')
        self.assertEqual(self.client.get('/api/projects').status_code, 403)
        grant(self.admin, User.objects.get(email=self.claims['email']), '使用者')
        response = self.client.get(login_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)

    def test_broker_denial_consumes_state_and_preserves_retry_destination(self):
        target = '/color.html?project=0123456789abcdef0123456789abcdef'
        state = self.begin(self.client, target)
        response = self.client.get('/auth/oidc/callback/', {'state': state, 'error': 'access_denied',
                                                          'error_description': '<script>untrusted</script>'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, '公司中心未授予此应用访问权限', status_code=400)
        self.assertEqual(response.context['next'], target)
        self.assertNotContains(response, '<script>', status_code=400)
        self.assertFalse(LoginRequest.objects.exists())
        self.assertEqual(self.finish(self.client, state).status_code, 400)

    def test_platform_admin_sees_only_assignable_accounts_and_roles(self):
        platform = User.objects.create_user(username='platform', email='platform@example.test')
        platform.groups.add(Group.objects.get_or_create(name='平台管理员')[0])
        member = User.objects.create_user(username='member', email='member@example.test')
        self.client.force_login(platform)
        data = self.client.get('/api/users').json()
        self.assertEqual(data['roles'], ['制作管理员', '运维人员', '使用者'])
        controls = {u['id']: u['canManage'] for u in data['users']}
        self.assertEqual(controls, {platform.pk: False, self.admin.pk: False, member.pk: True})
        for target, role in ((platform, '使用者'), (self.admin, '使用者'), (member, '超级管理员')):
            response = self.client.post('/api/users', {'user': target.pk, 'role': role}, content_type='application/json')
            self.assertEqual(response.status_code, 400)

    def test_authenticated_login_rejects_authentication_redirect_loops(self):
        self.client.force_login(self.admin)
        for target in ('/login/', '/login', '/auth/oidc/start/', '/auth/oidc/callback/', '/logout/'):
            with self.subTest(target=target):
                response = self.client.get('/login/', {'next': target})
                self.assertEqual(response.url, '/image-editor.html')

    def test_center_subpath_login_keeps_callback_and_destination_in_application(self):
        from config.urls import routes
        urls = ModuleType('shijie_subpath_test')
        urls.urlpatterns = [path('shijie/', include(routes))]
        with override_settings(PREFIX='/shijie', PUBLIC_URL='https://center.example/shijie', ROOT_URLCONF=urls):
            target = '/shijie/color.html?project=0123456789abcdef0123456789abcdef'
            self.assertContains(self.client.get('/shijie/login/'), '/shijie/static/server/home-atmosphere.js')
            self.assertEqual(self.client.get('/shijie/static/server/home-atmosphere.js').status_code, 200)
            gate = self.client.get(target)
            self.assertEqual(gate.status_code, 302)
            self.assertEqual(parse_qs(urlsplit(gate.url).query)['next'], [target])
            response = self.client.get('/shijie/auth/oidc/start/', {'next': target})
            query = parse_qs(urlsplit(response.url).query)
            self.assertEqual(query['redirect_uri'], ['https://center.example/shijie/auth/oidc/callback/'])
            with patch('shijie.accounts.views.exchange', return_value=self.claims):
                result = self.client.get('/shijie/auth/oidc/callback/', {'state': query['state'][0], 'code': 'valid'})
            self.assertEqual(result.url, target)
            self.assertEqual(self.client.get('/shijie/api/me').status_code, 403)
            grant(self.admin, User.objects.get(email=self.claims['email']), '使用者')
            self.assertEqual(self.client.get('/shijie/login/', {'next': target}).url, target)
            for outside in ('/image-editor.html', '//evil.test/', '/shijie/%2e%2e/admin/', '/shijie/login/'):
                self.assertEqual(self.client.get('/shijie/login/', {'next': outside}).url, '/shijie/image-editor.html')


class BrokerExchange(TestCase):
    """Use a real HTTP token endpoint: no mocks of exchange or provisioning."""
    def setUp(self):
        self.authorization = {}
        self.payload = {'email': ' Employee@Example.test ', 'name': '公司成员',
                        'expires_at': int(time.time()) + 3600}
        fixture = self

        class TokenEndpoint(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                fixture.headers = dict(self.headers)
                form = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
                verifier = form.get('code_verifier', [''])[0]
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                valid = (self.path == '/token' and fixture.authorization and
                         set(form) == {'grant_type', 'client_id', 'redirect_uri', 'code', 'code_verifier'} and
                         form['grant_type'] == ['authorization_code'] and form['code'] == ['single-use-code'] and
                         form['client_id'] == ['shijie-test'] and
                         form['redirect_uri'] == ['http://127.0.0.1:8090/auth/oidc/callback/'] and
                         fixture.authorization.get('code_challenge') == [challenge])
                fixture.authorization = {}
                self.send_response(200 if valid else 400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                payload = fixture.payload if valid else {'error': 'invalid_grant'}
                self.wfile.write((json.dumps(payload) if isinstance(payload, dict) else payload).encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), TokenEndpoint)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        config = {**BROKER, 'token_url': f'http://127.0.0.1:{server.server_port}/token',
                  'bootstrap_admin_emails': ['employee@example.test']}
        self.override = override_settings(OIDC=config, PUBLIC_URL='http://127.0.0.1:8090')
        self.override.enable()
        self.addCleanup(self.override.disable)

    def exchange(self):
        response = self.client.get('/auth/oidc/start/', {'next': '/queue/'})
        self.assertEqual(response.status_code, 302)
        self.authorization = parse_qs(urlsplit(response.url).query)
        state = self.authorization['state'][0]
        return self.client.get('/auth/oidc/callback/', {'state': state, 'code': 'single-use-code'})

    def test_real_pkce_exchange_bootstrap_and_no_regrant_after_revocation(self):
        response = self.exchange()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/queue/')
        self.assertEqual(self.client.get('/api/me').json()['roles'], ['超级管理员'])
        user = User.objects.get(email='employee@example.test')
        user.groups.clear()
        self.client.logout()
        self.assertEqual(self.exchange().status_code, 302)
        self.assertEqual(self.client.get('/api/me').status_code, 403)
        self.assertFalse(user.has_usable_password())

    def test_backend_exchange_uses_public_host_and_keeps_pkce(self):
        from django.conf import settings
        config = {**settings.OIDC, 'token_exchange_url': settings.OIDC['token_url'],
                  'token_url': 'https://identity.test.invalid:8443/auth/forward/token'}
        with override_settings(OIDC=config):
            response = self.exchange()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/queue/')
        self.assertEqual(self.headers['Host'], 'identity.test.invalid:8443')
        self.assertEqual(self.headers['X-Forwarded-Proto'], 'https')
        self.assertEqual(self.client.get('/api/me').status_code, 200)

    def test_untrusted_exchange_claims_never_create_accounts(self):
        for payload in ({**self.payload, 'expires_at': int(time.time()) - 1},
                        {**self.payload, 'expires_at': True},
                        {**self.payload, 'expires_at': int(time.time()) + 90000},
                        {**self.payload, 'email': 'not-an-email'},
                        {**self.payload, 'name': ''},
                        '{"email":"a@example.test","email":"b@example.test"}',
                        'x' * 65537):
            with self.subTest(kind=str(type(payload))):
                self.payload = payload
                self.assertEqual(self.exchange().status_code, 400)
                self.assertFalse(User.objects.exists())

    def test_disabled_company_account_cannot_sign_in(self):
        User.objects.create_user(username='disabled', email='employee@example.test', is_active=False)
        self.assertEqual(self.exchange().status_code, 400)
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_logout_requires_csrf_and_revokes_session(self):
        self.client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.exchange().status_code, 302)
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertEqual(self.client.post('/logout/').status_code, 403)
        csrf = self.client.get('/api/me').json()['csrf']
        self.assertEqual(self.client.post('/logout/', HTTP_X_CSRFTOKEN=csrf).status_code, 302)
        self.assertEqual(self.client.get('/api/me').status_code, 401)
