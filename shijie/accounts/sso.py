"""Company code + PKCE login; narrowed from TYComfyUI/accounts/sso.py (2026-10-13)."""
import json
import time
from functools import lru_cache
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from authlib.integrations.django_client import OAuth
from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from config.transport import broker_endpoint

class OIDCBackend(ModelBackend):
    def authenticate(self, request, **credentials):
        return None

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def callback_url():
    return settings.PUBLIC_URL + '/auth/oidc/callback/'

@lru_cache(maxsize=4)
def client(discovery, client_id, secret, auth_method):
    return OAuth().register('shijie', client_id=client_id, client_secret=secret,
        server_metadata_url=discovery, client_kwargs={'scope':'openid profile email',
        'code_challenge_method':'S256', 'token_endpoint_auth_method':auth_method, 'default_timeout':10})

def direct_client():
    c = settings.OIDC
    return client(c['discovery_url'], c['client_id'], c['client_secret'], c.get('token_endpoint_auth_method','client_secret_post'))

def validate_claims(value, direct=False):
    email, name = value.get('email'), value.get('name')
    if not isinstance(email,str) or not isinstance(name,str) or not 0 < len(name.strip()) <= 80:
        raise ValueError('身份信息不完整')
    email = email.strip().casefold()
    validate_email(email)
    expiry = value.get('exp' if direct else 'expires_at')
    if isinstance(expiry,bool) or not isinstance(expiry,(int,float)) or not time.time() < expiry <= time.time()+46860:
        raise ValueError('身份有效期无效')
    issuer, subject = '', ''
    if direct:
        issuer, subject = value.get('iss'), value.get('sub')
        if not all(isinstance(x,str) and 0 < len(x) <= 255 for x in [issuer,subject]):
            raise ValueError('OIDC 身份缺少 issuer / subject')
        if settings.OIDC.get('require_verified_email',True) and value.get('email_verified') is not True:
            raise ValueError('邮箱未验证')
    return {'email':email,'name':name.strip(),'expires':int(expiry),'issuer':issuer,'subject':subject}

def exchange(request, verifier):
    c = settings.OIDC
    if c.get('mode','direct') == 'direct':
        oauth = direct_client()
        token = oauth.authorize_access_token(request, leeway=60)
        identity = token.get('userinfo')
        profile = oauth.userinfo(token=token)
        if not isinstance(identity,dict) or not isinstance(profile,dict) or profile.get('sub') != identity.get('sub'):
            raise ValueError('OIDC UserInfo 身份不匹配')
        return validate_claims({**identity, **{k:v for k,v in profile.items() if k in ('email','name','email_verified')}},True)
    code = request.GET.get('code','')
    if not code or len(code)>512 or not code.isascii() or any(ord(x)<=32 or ord(x)==127 for x in code):
        raise ValueError('授权码无效')
    body = urlencode({'grant_type':'authorization_code','client_id':c['client_id'],'redirect_uri':callback_url(),'code':code,'code_verifier':verifier}).encode()
    endpoint = broker_endpoint(c)
    headers = {'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded'}
    if c.get('token_exchange_url'):
        public = urlsplit(c['token_url'])
        headers.update(Host=public.netloc, **{'X-Forwarded-Proto': public.scheme})
    req = Request(endpoint,data=body,headers=headers,method='POST')
    with build_opener(NoRedirect()).open(req,timeout=10) as response:
        raw = response.read(65537)
    if len(raw)>65536:
        raise ValueError('身份响应过大')
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result: raise ValueError('身份字段重复')
            result[k]=v
        return result
    result=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(result,dict):raise ValueError('身份响应无效')
    return validate_claims(result)
