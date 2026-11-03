"""Per-user model connections. Decrypted keys only cross the child process stdin."""
import base64
import hashlib
import json
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from .storage import user_root, write_json
from .company import idle


def path(user):
    return user_root(user.pk) / 'model-connections.json'


def read(user):
    return json.loads(path(user).read_text()) if path(user).exists() else {}


def cipher(user):
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f'shijie-models-v1:{user.pk}:{settings.SECRET_KEY}'.encode()).digest()))


@sensitive_variables()
def secret(user, provider):
    encrypted = read(user).get(provider, {}).get('key')
    if not encrypted:
        raise ValueError('请在模型设置中配置本人的' + ('太石' if provider == 'taishi' else '亿创') + ' Key')
    try:
        return cipher(user).decrypt(encrypted.encode()).decode()
    except (InvalidToken, UnicodeError):
        raise ValueError('连接密钥无法解密，请在模型设置中重新填写') from None


def image_status(user):
    value = read(user).get('aimake', {})
    return {'provider': value.get('provider', 'codex'), 'model': 'gpt-image-2',
            'configured': bool(value.get('key')), 'models': value.get('models', [])}


def models(user, provider):
    from . import ai, company
    if provider == 'auto': provider = ai.selected_provider(user)
    if provider == 'codex': return {**ai.status(user), 'provider': provider}
    if provider == 'company':
        value = company.status(user)
        ready = value['configured'] and value['enabled']
        return {'ready': ready, 'provider': provider, 'model': value['model'],
                'models': [{'id':value['model'], 'name':value['model']}] if ready else []}
    if provider != 'taishi': raise ValueError('模型来源无效')
    from assistant_models import gateway_models
    value = read(user).get('taishi', {})
    catalog = gateway_models(secret(user, provider)) if value.get('key') else []
    return {'ready': bool(catalog), 'provider': provider, 'models': catalog, 'model': catalog[0]['id'] if catalog else ''}


@sensitive_variables()
def save(user, data, provider):
    idle(user)
    from assistant_models import gateway_models
    from image_provider import catalog
    if not isinstance(data, dict) or (set(data) != {'key'} if provider == 'taishi' else
            set(data) - {'provider','model','key'} or data.get('provider') not in ('codex','aimake') or data.get('model') != 'gpt-image-2'):
        raise ValueError('模型连接参数无效')
    value = read(user)
    connection = value.setdefault(provider, {})
    if 'key' in data:
        key = data['key']
        if not isinstance(key, str) or not key or len(key)>4096 or any(not 33<=ord(c)<=126 for c in key):
            raise ValueError('请填写有效 Key，最多4096个ASCII可见字符')
        available = gateway_models(key) if provider == 'taishi' else catalog(key)
        if not available: raise ValueError('当前账号没有返回已适配的模型，原连接已保留')
        connection.update(key=cipher(user).encrypt(key.encode()).decode(), models=available)
    if provider == 'aimake':
        if data['provider'] == 'aimake' and not connection.get('key'): raise ValueError('请先填写本人亿创 Key')
        connection.update(provider=data['provider'], model=data['model'])
    write_json(path(user), value)
    return ({'ready': True, 'provider':'taishi', 'models':connection['models'], 'model':connection['models'][0]['id']}
            if provider == 'taishi' else {**image_status(user), 'ready':True})


@sensitive_variables()
def job_credentials(user, snapshot):
    from . import company
    uses_company = snapshot['provider']=='company' or snapshot.get('analysisProvider')=='company'
    base = company.credentials(user) if uses_company else {}
    if uses_company and not base: raise ValueError('公司 Agent 连接已停用')
    result = {'company': base, 'analysisProvider':snapshot.get('analysisProvider', snapshot['provider']),
              'image': {'provider':snapshot.get('imageProvider', 'codex'), 'model':'gpt-image-2'},
              'needsCodex': snapshot.get('needsCodex', snapshot['provider']=='codex')}
    if result['image']['provider'] == 'aimake': result['image']['key'] = secret(user, 'aimake')
    if result['analysisProvider'] == 'taishi': result['taishi'] = secret(user, 'taishi')
    return result
