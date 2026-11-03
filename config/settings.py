import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit, unquote
from .transport import validate_transport

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.environ.get('SHIJIE_PRODUCTION') == '1'
config_file = Path(os.environ.get('SHIJIE_CONFIG', BASE_DIR / '.local/config.toml'))
CONFIG = tomllib.loads(config_file.read_text()) if config_file.is_file() else {}
if PRODUCTION and (not config_file.is_file() or config_file.stat().st_mode & 0o077):
    raise ValueError('生产配置必须存在，且仅服务账号可读（0600）')
site = CONFIG.get('site', {})
SECRET_KEY = os.environ.get('SHIJIE_SECRET_KEY', site.get('secret_key', 'development-only-shijie-do-not-use-in-production'))
PUBLIC_URL = site.get('public_url', 'http://127.0.0.1:8093').rstrip('/')
public = validate_transport({**site, 'public_url': PUBLIC_URL}, CONFIG.get('oidc', {}), PRODUCTION)
PREFIX = public.path.rstrip('/')
if public.scheme not in ('http', 'https') or not public.hostname or public.query or public.fragment or public.username or public.password:
    raise ValueError('public_url 必须是 HTTP(S) 站点地址')
if any(x in PREFIX for x in ('..', '%', '\\')) or (PREFIX and not PREFIX.startswith('/')):
    raise ValueError('站点子路径无效')
if PRODUCTION and (len(SECRET_KEY) < 50 or 'development-only' in SECRET_KEY or 'replace-me' in SECRET_KEY):
    raise ValueError('生产环境必须使用独立随机 secret_key')
DEBUG = False
ALLOWED_HOSTS = [public.hostname, 'localhost', '127.0.0.1', 'testserver'] if not PRODUCTION else [public.hostname]
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.staticfiles', 'shijie.accounts', 'shijie.pipeline']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'shijie.accounts.middleware.AccessMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR/'shijie/templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth']}}]
DATABASE_URL = os.environ.get('SHIJIE_DATABASE_URL', CONFIG.get('database', {}).get('url', ''))
if DATABASE_URL:
    db = urlsplit(DATABASE_URL)
    if db.scheme not in ('postgresql', 'postgres') or db.query or db.fragment:
        raise ValueError('仅支持 PostgreSQL database.url；连接选项通过服务配置设置')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(db.path.lstrip('/')), 'USER': unquote(db.username or ''), 'PASSWORD': unquote(db.password or ''), 'HOST': db.hostname or '127.0.0.1', 'PORT': db.port or 5432, 'CONN_MAX_AGE': 30}}
elif PRODUCTION:
    raise ValueError('生产环境必须配置 PostgreSQL')
else:
    (BASE_DIR/'.local').mkdir(exist_ok=True)
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR/'.local/dev.sqlite3', 'OPTIONS': {'timeout': 20}}}
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['shijie.accounts.sso.OIDCBackend']
SESSION_COOKIE_NAME = 'shijie_sessionid'
CSRF_COOKIE_NAME = 'shijie_csrftoken'
SESSION_COOKIE_PATH = CSRF_COOKIE_PATH = PREFIX + '/'
SESSION_COOKIE_AGE = 12*60*60
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = PRODUCTION and public.scheme == 'https'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = [f'{public.scheme}://{public.netloc}']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = PRODUCTION and public.scheme == 'https'
SECURE_HSTS_SECONDS = 86400 if SECURE_SSL_REDIRECT else 0
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = PREFIX + '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
STATICFILES_DIRS = [BASE_DIR/'shijie/static']
FILE_UPLOAD_MAX_MEMORY_SIZE = 2*1024**2
OIDC = CONFIG.get('oidc', {})
DATA_ROOT = Path(os.environ.get('SHIJIE_DATA_ROOT', CONFIG.get('storage', {}).get('root', str(BASE_DIR/'.local/data')))).resolve()
LEGACY_ROOT = BASE_DIR/'legacy'
WORKER = CONFIG.get('worker', {})
JOB_TIMEOUT = int(WORKER.get('timeout_seconds', 7200))
LOCAL_MODEL_ROOT = Path(os.environ.get('SHIJIE_LOCAL_MODEL_ROOT', BASE_DIR / '.local/local-model')).resolve()
MAX_QUEUED_PER_USER = int(WORKER.get('queued_per_user', 5))
DATA_UPLOAD_MAX_MEMORY_SIZE = 276 * 1024**2
MIN_FREE = int(CONFIG.get('storage', {}).get('min_free_mib', 1024)) * 1024**2
USER_QUOTA = int(CONFIG.get('storage', {}).get('user_quota_gib', 20)) * 1024**3
if min(JOB_TIMEOUT, MAX_QUEUED_PER_USER, MIN_FREE, USER_QUOTA) <= 0:
    raise ValueError('容量、队列和超时必须为正数')
ENGINE_ROOT = LEGACY_ROOT / '拾界插件/开发源码/自动拆图'
EDITOR_ROOT = LEGACY_ROOT / '拾界插件/插件程序/edge'
import sys
sys.path.insert(0, str(ENGINE_ROOT))
