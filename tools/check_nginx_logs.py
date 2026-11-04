"""Exercise the deployment example with dummy OIDC values and a local upstream.

Run: python3 tools/check_nginx_logs.py
Requires the existing nginx:1.28-alpine Docker image; never pulls or calls SSO.
"""
import subprocess
import tempfile
import time
from pathlib import Path


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, capture_output=True, text=True)


def main():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'deploy/nginx.conf.example').read_text()
    before, separator, locations = template.partition('location ')
    assert separator, 'deployment example has no location'
    with tempfile.TemporaryDirectory(prefix='shijie-nginx-') as temporary:
        folder = Path(temporary)
        config = folder / 'nginx.conf'
        config.write_text('''error_log /var/log/nginx/error.log warn;
events {}
http {
    access_log /var/log/nginx/inherited-access.log combined;
''' + before + '''
    server {
        listen 8093;
        access_log off;
        location / {
            if ($arg_case = unavailable) { return 444; }
            return 204;
        }
    }
    server {
        listen 8080;
        server_name localhost;
''' + separator + locations + '\n}\n}\n')
        container = docker('run', '--rm', '-d', '--pull=never', '--network=none',
                           '-v', f'{config}:/etc/nginx/nginx.conf:ro',
                           '-v', f'{folder}:/var/log/nginx', '--entrypoint', 'nginx',
                           'nginx:1.28-alpine', '-g', 'daemon off;').stdout.strip()
        try:
            for _ in range(30):
                if docker('exec', container, 'wget', '-q', '-O', '/dev/null',
                          'http://127.0.0.1:8093/', check=False).returncode == 0:
                    break
                time.sleep(.1)
            else:
                raise AssertionError('isolated nginx did not start')
            # Literal sentinels are test values, never account credentials.
            sentinels = ['audit-code-sentinel', 'audit-state-sentinel', 'audit-referer-sentinel']
            for path, case, status in [('/shijie/auth/oidc/callback/', 'ok', '204'),
                                       ('/shijie/auth/oidc/callback/', 'unavailable', '502'),
                                       ('/shijie', 'ok', '302')]:
                url = ('http://127.0.0.1:8080' + path +
                       f'?code={sentinels[0]}&state={sentinels[1]}&case={case}')
                response = docker('exec', container, 'wget', '-S', '-O', '/dev/null',
                                  '--header=Referer: https://login.example.test/?code=' + sentinels[2],
                                  url, check=False)
                assert f'HTTP/1.1 {status}' in response.stderr, 'unexpected proxy status'
            docker('stop', '-t', '3', container)
        finally:
            docker('rm', '-f', container, check=False)
        logs = '\n'.join(p.read_text() for p in folder.glob('*.log'))
        assert '/shijie/auth/oidc/callback/' in logs, 'missing useful access log'
        assert all(status in logs for status in ('204', '502', '302')), 'missing success/failure/redirect status'
        assert not any(value in logs for value in sentinels), 'OIDC query or Referer leaked into nginx logs'
    print('PASS: real nginx records route/status for 204, 502 and 302; no OIDC query or Referer sentinels in access/error logs.')


if __name__ == '__main__':
    main()
