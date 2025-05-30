# accounts/urls.py

from django.urls import path
from .views import register_user, login_user, login_success

urlpatterns = [
    path("register/", register_user, name="register_user"),
    path("login/", login_user, name="login_user"),
    path("success/", login_success, name="login_success"),
]
