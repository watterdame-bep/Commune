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
from django.urls import include, path

from sisepcommune import views
from referentiel_geo import views as geo_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
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
    path('documents/telecharger/<int:pk>/', views.document_download_view, name='document_download'),
    path('documents/', views.documents_view, name='documents'),
    path('galerie/', views.public_gallery_view, name='public_gallery'),
    path('ministere/', views.ministere_dashboard_view, name='ministere_dashboard'),
    path('ministere/galerie/', views.ministere_gallery_view, name='ministere_gallery'),
    path('ministere/galerie/<int:pk>/', views.ministere_gallery_edit_view, name='ministere_gallery_edit'),
    path('ministere/galerie/<int:pk>/supprimer/', views.ministere_gallery_delete_view, name='ministere_gallery_delete'),
    path('ministere/referentiel-geo/provinces/', geo_views.ministere_provinces_view, name='ministere_provinces'),
    path('ministere/referentiel-geo/provinces/nouvelle/', geo_views.ministere_province_create_view, name='ministere_province_create'),
    path('ministere/referentiel-geo/provinces/<int:pk>/modifier/', geo_views.ministere_province_edit_view, name='ministere_province_edit'),
    path('ministere/referentiel-geo/provinces/<int:pk>/supprimer/', geo_views.ministere_province_delete_view, name='ministere_province_delete'),
    path('ministere/referentiel-geo/provinces/initialiser/', geo_views.ministere_provinces_initialize_all_view, name='ministere_provinces_initialize_all'),
    path('ministere/referentiel-geo/provinces/name-exists/', geo_views.ministere_province_name_exists_view, name='ministere_province_name_exists'),
    path('ministere/referentiel-geo/villes/', geo_views.ministere_geo_villes_view, name='ministere_geo_villes'),
    path('ministere/referentiel-geo/communes/', geo_views.ministere_geo_communes_view, name='ministere_geo_communes'),
    path('ministere/referentiel-geo/quartiers/', geo_views.ministere_geo_quartiers_view, name='ministere_geo_quartiers'),
    path('ministere/villes/', views.ministere_villes_view, name='ministere_villes'),
    path('hdv/', views.hdv_dashboard_view, name='hdv_dashboard'),
    path('hdv/communes/', views.hdv_communes_view, name='hdv_communes'),
    path('hdv/communes/nouvelle/', views.hdv_commune_create_view, name='hdv_commune_create'),
    path('hdv/communes/<int:pk>/', views.hdv_commune_edit_view, name='hdv_commune_edit'),
    path('hdv/referentiel-geo/', views.hdv_geo_view, name='hdv_geo'),
    path('hdv/utilisateurs/', views.hdv_users_view, name='hdv_users'),
    path('hdv/activites/', views.hdv_activites_view, name='hdv_activites'),
    path('hdv/dossiers-sensibles/', views.hdv_dossiers_sensibles_view, name='hdv_dossiers_sensibles'),
    path('hdv/annonces/', views.hdv_annonces_view, name='hdv_annonces'),
    path('hdv/audit/', views.hdv_audit_view, name='hdv_audit'),
    path('hdv/galerie/', views.hdv_gallery_view, name='hdv_gallery'),
    path('hdv/galerie/<int:pk>/', views.hdv_gallery_edit_view, name='hdv_gallery_edit'),
    path('hdv/galerie/<int:pk>/supprimer/', views.hdv_gallery_delete_view, name='hdv_gallery_delete'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
