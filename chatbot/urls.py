from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

def redirect_to_login(request):
    return redirect('login_user')
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', redirect_to_login),  # root now redirects to login
    path('chat/', include('chat.urls')),  # chatbot now under /chat/
    path('accounts/', include('accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
