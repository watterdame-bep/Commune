"""
URL configuration for sisepcommune project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from sisepcommune import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.welcome, name='welcome'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('password-reset/', views.password_reset_request_view, name='password_reset'),
    path('password-reset/verify/', views.password_reset_verify_view, name='password_reset_verify'),
    path('register/sent/', views.register_sent_view, name='register_sent'),
    path('confirm-email/<str:token>/', views.confirm_email_view, name='confirm_email'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('demandes/nouvelle/', views.demande_create_view, name='demande_create'),
    path('demandes/<int:pk>/', views.demande_detail_view, name='demande_detail'),
    path('demandes/', views.demandes_view, name='demandes'),
    path('documents/', views.documents_view, name='documents'),
    path('hdv/', views.hdv_dashboard_view, name='hdv_dashboard'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
