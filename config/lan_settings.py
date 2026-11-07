"""Explicit Windows LAN profile; never loaded by the public server deployment."""
import ipaddress
import json
import os
from pathlib import Path

LAN_STATE = Path(os.environ['SHIJIE_LAN_STATE']).resolve()
LAN_CONFIG = json.loads((LAN_STATE / 'site.json').read_text('utf8'))
os.environ['SHIJIE_CONFIG'] = str(LAN_STATE / 'server.toml')
os.environ['SHIJIE_DATA_ROOT'] = str(LAN_STATE / 'data')
os.environ['SHIJIE_PRODUCTION'] = '0'
from .settings import *

LAN_SHARED = True
host = ipaddress.IPv4Address(LAN_CONFIG['host'])
if not host.is_private or host.is_loopback or host.is_link_local:
    raise ValueError('局域网共享只接受公司内网 IPv4 地址')
LAN_NETWORK = ipaddress.ip_network(f"{host}/{int(LAN_CONFIG['prefix_length'])}", strict=False)
if LAN_NETWORK.prefixlen < 16:
    raise ValueError('局域网范围过大，请使用具体办公网段')
port = int(LAN_CONFIG['port'])
if not 1024 <= port <= 65535:
    raise ValueError('共享端口无效')
SECRET_KEY = LAN_CONFIG['secret_key']
if len(SECRET_KEY) < 50 or len(LAN_CONFIG['access_digest']) != 64:
    raise ValueError('局域网访问配置无效')
PREFIX = ''
PUBLIC_URL = f'http://{host}:{port}'
ALLOWED_HOSTS = [str(host), '127.0.0.1', 'localhost', 'testserver']
ROOT_URLCONF = 'config.lan_urls'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': LAN_STATE / 'lan.sqlite3',
    'OPTIONS': {'timeout': 30, 'transaction_mode': 'IMMEDIATE'}}}
SESSION_COOKIE_NAME = 'shijie_lan_sessionid'
CSRF_COOKIE_NAME = 'shijie_lan_csrftoken'
SESSION_COOKIE_PATH = CSRF_COOKIE_PATH = '/'
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = [PUBLIC_URL, f'http://127.0.0.1:{port}', f'http://localhost:{port}']
SECURE_PROXY_SSL_HEADER = None
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
MIDDLEWARE = ['shijie.accounts.lan.NetworkBoundary', *MIDDLEWARE]
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware')+1, 'shijie.accounts.lan.OwnerBoundary')
STATIC_URL = '/static/'
OIDC = {}
