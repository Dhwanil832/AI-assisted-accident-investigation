# accounts/urls.py

from django.urls import path
from .views import register_user, login_user, login_success, logout_user

urlpatterns = [
    path("register/", register_user, name="register_user"),
    path("login/", login_user, name="login_user"),
    path("success/", login_success, name="login_success"),
    path("logout/", logout_user, name="logout_user"),

]
