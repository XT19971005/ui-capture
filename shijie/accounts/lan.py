"""Access-code admission and separate browser identities for a trusted office LAN."""
import hashlib
import ipaddress
import secrets
import threading
import time
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from .models import User
from .services import allowed, is_admin
from .views import safe_next

_attempts = {}
_lock = threading.Lock()


def loopback(request):
    # The HTTPS listener is always a colleague entrance, including on the host PC.
    if getattr(settings, 'LAN_HTTPS', False):
        return False
    try:
        return ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')).is_loopback
    except ValueError:
        return False


class NetworkBoundary:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            address = ipaddress.ip_address(request.META.get('REMOTE_ADDR', ''))
            if not address.is_loopback and address not in settings.LAN_NETWORK:
                return HttpResponseForbidden('此入口只供同一办公局域网使用。')
        except ValueError:
            return HttpResponseForbidden('访问来源无效。')
        # Relay bearer credentials and service control stay on this PC's loopback.
        if request.path.startswith('/desktop-relay/') and (getattr(settings, 'LAN_HTTPS', False) or not address.is_loopback):
            return HttpResponseForbidden('本机接单通道不接受局域网请求。')
        return self.get_response(request)


class OwnerBoundary:
    """Placed after authentication so an owner cookie cannot be replayed over the LAN."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_admin(request.user) and not loopback(request):
            return HttpResponseForbidden('管理员入口仅限本机打开。')
        return self.get_response(request)


def _identity(request):
    if loopback(request):
        name, label = 'lan-owner', '本机管理员'
    else:
        name = request.get_signed_cookie('shijie_lan_identity', default='', salt='lan-browser', max_age=90*86400)
        if not name.startswith('lan-guest-') or len(name) != 42:
            name = 'lan-guest-' + uuid4().hex
        label = '局域网使用者 ' + name[-6:]
    user, created = User.objects.get_or_create(username=name, defaults={
        'email': name + '@local.invalid', 'display_name': label, 'is_superuser': name == 'lan-owner'})
    if created:
        user.set_unusable_password(); user.save(update_fields=['password'])
        if not user.is_superuser:
            user.groups.add(Group.objects.get_or_create(name='使用者')[0])
    return user


@require_http_methods(['GET', 'POST'])
def login_page(request):
    nxt = safe_next(request.POST.get('next', request.GET.get('next', '')))
    admitted = allowed(request.user)
    if admitted and not (request.method == 'GET' and request.GET.get('entry') == '1'):
        return redirect(nxt)
    context = {'next': nxt, 'already_allowed': admitted}
    status = 200
    if request.method == 'POST':
        peer = request.META.get('REMOTE_ADDR', '')
        now = time.monotonic()
        code = request.POST.get('access_code', '').strip()
        with _lock:
            for key in list(_attempts):
                if now - _attempts[key][0] > 300:
                    del _attempts[key]
            since, count = _attempts.get(peer, (now, 0))
            limited = count >= 8 or len(_attempts) >= 1024 and peer not in _attempts
            valid = not limited and len(code) <= 80 and secrets.compare_digest(
                hashlib.sha256(code.encode()).hexdigest(), settings.LAN_CONFIG['access_digest'])
            if not valid and not limited:
                _attempts[peer] = (since, count + 1)
            elif valid:
                _attempts.pop(peer, None)
        if limited:
            context['error'] = '尝试次数过多，请五分钟后再试。'; status = 429
        elif not valid:
            context['error'] = '访问码不正确，请向共享电脑的管理员获取。'; status = 400
        else:
            user = _identity(request)
            if not allowed(user):
                return HttpResponseForbidden('此浏览器的使用权限已被停用。')
            login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
            if getattr(settings, 'LAN_HTTPS', False):
                request.session.set_expiry(90*86400)
            response = redirect(nxt)
            if not user.is_superuser:
                response.set_signed_cookie('shijie_lan_identity', user.username, salt='lan-browser',
                    max_age=90*86400, httponly=True, samesite='Lax', secure=request.is_secure())
            return response
    return render(request, 'lan-login.html', context, status=status)
