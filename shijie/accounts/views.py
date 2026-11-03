import base64
import hashlib
import secrets
import time
from datetime import timedelta
from urllib.parse import urlsplit,unquote,urlencode
from django.conf import settings
from django.contrib.auth import login,logout
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render,redirect
from django.utils import timezone
from django.views.decorators.http import require_GET,require_POST
from .models import LoginRequest
from .services import provision,allowed
from .sso import callback_url,direct_client,exchange

def safe_next(value):
    try:
        p=urlsplit(value);decoded=unquote(value);path=unquote(p.path).rstrip('/')
        if (len(value)<=2048 and not p.scheme and not p.netloc and p.path.startswith(settings.PREFIX+'/') and
            not decoded.startswith('//') and '\\' not in decoded and not any(ord(c)<32 for c in decoded) and
            path not in (settings.PREFIX+'/login',settings.PREFIX+'/logout') and not path.startswith(settings.PREFIX+'/auth/') and
            not any(x in ('.','..') for x in unquote(p.path).split('/'))):return value
    except ValueError:pass
    return settings.PREFIX+'/image-editor.html'

@require_GET
def login_page(request):
    nxt=safe_next(request.GET.get('next',''))
    if allowed(request.user):return redirect(nxt)
    return render(request,'login.html',{'prefix':settings.PREFIX,'next':nxt,'pending':request.user.is_authenticated})

@require_GET
def start(request):
    nxt=safe_next(request.GET.get('next',''))
    if request.user.is_authenticated:
        return redirect(nxt) if allowed(request.user) else login_page(request)
    c=settings.OIDC
    needed=('discovery_url','client_id','client_secret') if c.get('mode','direct')=='direct' else ('login_url','token_url','client_id')
    if not all(c.get(k) for k in needed):return render(request,'login.html',{'prefix':settings.PREFIX,'next':nxt,'error':'公司登录尚未配置，请联系管理员。'},status=503)
    if request.session.session_key is None:request.session.create()
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    LoginRequest.objects.filter(expires_at__lte=timezone.now()).delete()
    retained=list(LoginRequest.objects.filter(session_key=request.session.session_key).order_by('-id').values_list('id',flat=True)[:4])
    LoginRequest.objects.filter(session_key=request.session.session_key).exclude(id__in=retained).delete()
    LoginRequest.objects.create(digest=hashlib.sha256(state.encode()).hexdigest(),session_key=request.session.session_key,verifier=verifier,next_url=nxt,expires_at=timezone.now()+timedelta(minutes=10))
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    try:
        if c.get('mode','direct')=='direct':
            response=direct_client().authorize_redirect(request,callback_url(),state=state,code_verifier=verifier)
        else:
            response=redirect(c['login_url']+('?' if '?' not in c['login_url'] else '&')+urlencode({'response_type':'code','client_id':c['client_id'],'redirect_uri':callback_url(),'state':state,'code_challenge':challenge,'code_challenge_method':'S256'}))
        response['Cache-Control']='no-store';response['Referrer-Policy']='no-referrer';return response
    except Exception:
        LoginRequest.objects.filter(digest=hashlib.sha256(state.encode()).hexdigest()).delete()
        return render(request,'login.html',{'prefix':settings.PREFIX,'next':nxt,'error':'公司登录暂时不可用。'},status=503)

@require_GET
def callback(request):
    nxt=settings.PREFIX+'/image-editor.html'
    error='登录校验失败或已过期，请重新登录。'
    try:
        if len(request.GET.getlist('state'))!=1 or not 1<=len(request.GET['state'])<=512:raise ValueError('无效回调')
        with transaction.atomic():
            pending=LoginRequest.objects.select_for_update().filter(digest=hashlib.sha256(request.GET['state'].encode()).hexdigest(),session_key=request.session.session_key or '',expires_at__gt=timezone.now()).first()
            if pending is None:raise ValueError('已过期或重放')
            pending.delete()
        nxt=safe_next(pending.next_url)
        if 'error' in request.GET:
            if len(request.GET.getlist('error'))==1 and 'code' not in request.GET and request.GET['error']=='access_denied':
                error='公司中心未授予此应用访问权限，或本次登录已取消。请联系管理员后重试。'
            raise ValueError('公司授权未完成')
        if len(request.GET.getlist('code'))!=1:raise ValueError('无效回调')
        claims=exchange(request,pending.verifier)
        user=provision(claims)
        if not user.is_active:raise ValueError('账号已停用')
        old=request.session.session_key
        login(request,user,backend=settings.AUTHENTICATION_BACKENDS[0])
        LoginRequest.objects.filter(session_key=old).update(session_key=request.session.session_key)
        request.session.set_expiry(max(1,min(claims['expires']-int(time.time()),settings.SESSION_COOKIE_AGE)))
        response=redirect(nxt)
    except Exception:
        # Do not echo provider responses, authorization codes or tokens in logs/UI.
        response=render(request,'login.html',{'prefix':settings.PREFIX,'next':nxt,'error':error},status=400)
    response['Cache-Control']='no-store';response['Referrer-Policy']='no-referrer';return response

@require_POST
def signout(request):
    logout(request)
    return redirect(settings.PREFIX+'/login/')
