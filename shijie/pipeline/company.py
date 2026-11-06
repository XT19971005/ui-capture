"""Private company Agent settings; only the job process receives decrypted credentials."""
import base64
import hashlib
import json
import re
import secrets
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from PIL import Image
import company_agent
from .models import Job
from .storage import user_root, write_json, connection_version, commit_connection


def path(user):
    return user_root(user.pk) / 'company-agent.json'


def read(user):
    return json.loads(path(user).read_text()) if path(user).exists() else {}


def cipher(user):
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f'shijie-company-v1:{user.pk}:{settings.SECRET_KEY}'.encode()).digest()))


def status(user):
    value = read(user)
    return {'ok': True, 'configured': bool(value.get('key')), 'enabled': value.get('enabled', False),
            'model': value.get('model', ''), 'endpoint': company_agent.ENDPOINT,
            'imageGeneration': True, 'verified': bool(value.get('checkedAt')), 'checkedAt': value.get('checkedAt')}


@sensitive_variables()
def credentials(user, *, include_disabled=False):
    value = read(user)
    if not value or (not value.get('enabled') and not include_disabled): return None
    try:
        return {'api_key': cipher(user).decrypt(value['key'].encode()).decode(), 'model': value['model']}
    except (InvalidToken, KeyError):
        raise ValueError('公司 Agent Key 无法解密，请重新保存连接') from None


def idle(user):
    if Job.objects.filter(owner=user, status__in=['queued', 'running']).exists():
        raise ValueError('请先完成或取消当前任务，再修改或测试 AI 连接')


@sensitive_variables()
def save(user, data):
    idle(user)
    if not isinstance(data, dict) or set(data) != {'api_key', 'model', 'enabled'}:
        raise ValueError('公司 Agent 连接参数无效')
    key, model = data['api_key'], data['model']
    if not isinstance(key, str) or len(key) > 4096 or any(not 33 <= ord(c) <= 126 for c in key):
        raise ValueError('公司 Agent Key 格式无效，最多 4096 字符')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}', model):
        raise ValueError('请填写公司接口可用的模型 ID，最多 120 字符')
    if type(data['enabled']) is not bool: raise ValueError('启用状态无效')
    previous = read(user)
    if not key and not previous.get('key'): raise ValueError('请先填写公司 Agent API Key')
    value = {'key': cipher(user).encrypt(key.encode()).decode() if key else previous['key'],
             'model': model, 'enabled': data['enabled'],
             'checkedAt': previous.get('checkedAt') if not key and model == previous.get('model') else None}
    write_json(path(user), value)
    return status(user)


@sensitive_variables()
def probe(user):
    idle(user)
    version=connection_version(path(user))
    config = credentials(user, include_disabled=True)
    if config is None: raise ValueError('请先保存公司 Agent 连接')
    value = read(user)
    value['checkedAt'] = None
    version=commit_connection(user,path(user),version,value)
    colors = {'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255)}
    chosen = secrets.choice(list(colors))
    with tempfile.TemporaryDirectory(prefix='company-probe-', dir=user_root(user.pk)) as folder:
        picture = Path(folder) / 'connection-test.png'
        Image.new('RGB', (32, 32), colors[chosen]).save(picture)
        schema = {'type': 'object', 'required': ['color'], 'additionalProperties': False,
                  'properties': {'color': {'type': 'string', 'enum': list(colors)}}}
        try:
            result = company_agent.analyze(config, '请识别附件色块的颜色。', [picture], schema, root=Path(folder), timeout=60)
        except company_agent.CompanyError as exc:
            raise ValueError(str(exc)) from None
        if result['color'] != chosen: raise ValueError('公司 Agent 未正确识别测试图片，请选择支持视觉分析的模型')
    value['checkedAt'] = timezone.now().isoformat()
    commit_connection(user,path(user),version,value)
    return status(user)
