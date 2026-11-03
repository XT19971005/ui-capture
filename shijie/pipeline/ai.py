import json
import shutil
import time
import uuid
import fcntl
import subprocess
import tempfile
import requests
from pathlib import Path
from django.views.decorators.debug import sensitive_variables
from .models import Job
from .storage import user_root, write_json
from .processes import start, stop, environment


def home(user):
    return user_root(user.pk) / 'codex'


def execute(user, action, codex_home=None):
    root = user_root(user.pk) / 'ai-requests' / str(uuid.uuid4())
    process = start('ai_session.py', root, codex_home or home(user), action, user.codex_model)
    result = root / 'response.json'
    for _ in range(120):
        if result.exists():
            value = json.loads(result.read_text())
            if action != 'login':
                process.wait(timeout=10)
                shutil.rmtree(root)
            return value
        if process.poll() is not None:
            break
        time.sleep(0.25)
    stop(process)
    return {'ok': False, 'ready': False, 'error': 'Codex 连接未成功，请检查服务器网络和运行环境后重试'}


@sensitive_variables()
def status(user):
    auth_file = home(user) / 'auth.json'
    if auth_file.is_file():
        try:
            auth = json.loads(auth_file.read_text())
        except (ValueError, OSError):
            return {'ok': False, 'ready': False, 'error': 'Codex 凭据无法读取，请在 AI 连接中重新连接'}
        if not isinstance(auth, dict):
            return {'ok': False, 'ready': False, 'error': 'Codex 凭据格式无效，请在 AI 连接中重新连接'}
        if auth.get('auth_mode') == 'apikey':
            try:
                verify_api_key(auth.get('OPENAI_API_KEY'))
            except ValueError as exc:
                return {'ok': False, 'ready': False, 'provider': 'apiKey', 'imageGeneration': False, 'models': [], 'error': str(exc)}
    return {**execute(user, 'status'), 'pending': pending_login(user)}


def pending_login(user, internal=False):
    directory = home(user)
    if not directory.exists():
        return None
    with (directory / 'account.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            (directory / 'device-login.json').unlink(missing_ok=True)
            return None
        try:
            value = json.loads((directory / 'device-login.json').read_text())
            ident = str(uuid.UUID(value['requestId']))
            if value['expiresAt'] <= time.time() or value['url'] != 'https://auth.openai.com/codex/device':
                return None
            result = {key: value[key] for key in ('url', 'userCode', 'expiresAt')}
            return {**result, 'requestId': ident} if internal else result
        except (OSError, ValueError, KeyError, TypeError):
            return None


def cancel_login(user):
    pending = pending_login(user, internal=True)
    if pending:
        root = user_root(user.pk) / 'ai-requests' / pending['requestId']
        write_json(root / 'cancel', {})
        for _ in range(40):
            if not pending_login(user):
                break
            time.sleep(.1)
        else:
            raise ValueError('上次登录仍在结束，请稍后再试；当前账号未更改')
    return {'ok': True}


def login(user):
    if Job.objects.filter(owner=user, status__in=['queued', 'running']).exists():
        raise ValueError('请先完成或取消当前任务，再切换 AI 账号')
    pending = pending_login(user)
    return {'ok': True, **pending} if pending else execute(user, 'login')


def logout(user):
    if Job.objects.filter(owner=user, status__in=['queued', 'running']).exists():
        raise ValueError('请先完成或取消当前任务，再退出 AI 账号')
    cancel_login(user)
    return execute(user, 'logout')


@sensitive_variables('token')
def access_token(user, token, *, api_key=False):
    label = 'OpenAI API Key' if api_key else 'Codex 访问令牌'
    if not isinstance(token, str) or not 20 <= len(token) <= 8192 or any(not 33 <= ord(c) <= 126 for c in token):
        raise ValueError(f'请输入有效的 {label}，最多 8192 个字符')
    if Job.objects.filter(owner=user, status__in=['queued', 'running']).exists():
        raise ValueError('请先完成或取消当前任务，再切换 AI 账号')
    if api_key:
        verify_api_key(token)
    cancel_login(user)
    directory = home(user)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'account.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('账号操作正在进行，请稍后重试')
        # Validate in a disposable home so a rejected token cannot replace a working account.
        with tempfile.TemporaryDirectory(prefix='token-check-', dir=directory) as temporary:
            staged = Path(temporary)
            env = environment(staged, staged)
            cli = shutil.which('codex', path=env['PATH'])
            if not cli:
                raise ValueError('服务器 Codex 未安装，请联系管理员')
            try:
                result = subprocess.run([cli, 'login', '--with-api-key' if api_key else '--with-access-token', '-c', 'cli_auth_credentials_store="file"'],
                                        input=token, text=True, env=env, cwd=staged, timeout=25,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                raise ValueError(f'{label} 连接超时，请稍后重试；原有连接已保留')
            if result.returncode or not (staged / 'auth.json').is_file():
                if api_key:
                    raise ValueError('OpenAI API Key 未能连接 Codex；原有连接已保留，请检查服务网络后重试')
                raise ValueError('Codex 访问令牌未通过验证。OpenAI 平台 API Key 请使用“OpenAI API Key”入口，公司 Key 请填在“公司 Agent”。若已使用团队访问令牌，请检查有效期及工作区权限')
            state = execute(user, 'status', codex_home=staged)
            if not state.get('ok') or not state.get('ready'):
                raise ValueError(f'暂时无法验证 {label} 的连接，原有连接已保留；请检查模型权限或稍后重试')
            write_json(directory / 'auth.json', json.loads((staged / 'auth.json').read_text()))
            return state


@sensitive_variables()
def verify_api_key(key):
    if not isinstance(key, str) or not 20 <= len(key) <= 8192 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError('OpenAI API Key 格式无效，请重新填写')
    # ponytail: a read-only models request verifies auth without paid inference or retries.
    # It cannot establish model-specific billing/quota; actual jobs still validate their result.
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.get('https://api.openai.com/v1/models', headers={'Authorization': 'Bearer ' + key},
                            stream=True, timeout=(10, 20), allow_redirects=False) as response:
                code = response.status_code
                if code == 200:
                    return
                message = {401: 'Key 无效或已撤销，请重新填写',
                           403: '访问被拒绝，请检查 API 项目权限（含 Models 读取权限）或地区限制',
                           429: '请求受限，请检查 API 项目额度、计费及限流'}.get(code, '服务暂时不可用，请稍后重试')
                raise ValueError(f'OpenAI API Key 验证失败（HTTP {code}）：{message}')
    except requests.RequestException:
        raise ValueError('OpenAI API 网络连接失败，请检查拾界服务器到 api.openai.com 的网络；未自动重试') from None


def selected_provider(user):
    from . import company
    # A configured Codex wins even if its token is expired. Never replay on another provider.
    if (home(user) / 'auth.json').is_file():
        return 'codex'
    return 'company' if company.status(user)['enabled'] else 'codex'


def connections(user):
    from . import company
    configured = (home(user) / 'auth.json').is_file()
    codex = status(user) if configured else {'ok': True, 'ready': False, 'models': [], 'imageGeneration': False, 'pending': pending_login(user)}
    codex['configured'] = configured
    return {'ok': True, 'active': selected_provider(user), 'company': company.status(user), 'codex': codex}
