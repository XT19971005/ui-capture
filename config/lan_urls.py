from django.urls import path
from shijie.accounts.lan import login_page
from .urls import routes

urlpatterns = [path('login/', login_page), *routes]
