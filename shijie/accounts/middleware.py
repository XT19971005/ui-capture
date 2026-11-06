from urllib.parse import urlencode
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers
from .services import allowed


class AccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.removeprefix(settings.PREFIX)
        public = path in ('/login/', '/auth/oidc/start/', '/auth/oidc/callback/', '/logout/', '/health/live', '/health/ready', '/desktop-relay/v1/heartbeat', '/desktop-relay/v1/claim', '/desktop-relay/v1/start', '/desktop-relay/v1/update', '/desktop-relay/v1/artifact') or path.startswith('/static/server/')
        if not public and not allowed(request.user):
            response = (JsonResponse({'error': '账号待授权' if request.user.is_authenticated else '请登录'}, status=403 if request.user.is_authenticated else 401)
                        if path.startswith('/api/') else redirect(settings.PREFIX + '/login/?' + urlencode({'next': request.get_full_path()})))
        elif not public and request.headers.get('X-Shijie-User', str(request.user.pk)) != str(request.user.pk):
            response = JsonResponse({'error': '登录账号已变化，请重新打开页面；当前修改可导出备份'}, status=409)
        else:
            response = self.get_response(request)
        add_never_cache_headers(response)
        return response
