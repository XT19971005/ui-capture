from django.conf import settings
from django.urls import path, re_path, include
from shijie.accounts import views as auth
from shijie.pipeline import views
from shijie.pipeline.desktop_service import relay

routes = [path('login/', auth.login_page), path('auth/oidc/start/', auth.start),
          re_path(r'^desktop-relay/v1/(?P<action>heartbeat|claim|start|update|artifact)$', relay),
          path('auth/oidc/callback/', auth.callback), path('logout/', auth.signout),
          path('health/live', views.live), path('health/ready', views.ready),
          re_path(r'^api/(?P<route>.*)$', views.api), re_path(r'^(?P<page>.*)$', views.page)]
urlpatterns = [path(settings.PREFIX.lstrip('/') + '/', include(routes))] if settings.PREFIX else routes
