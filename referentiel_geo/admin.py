from django.contrib import admin

from referentiel_geo.models import Commune, Province, Ville


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("nom", "chef_lieu", "population_estimee", "superficie_km2", "active", "updated_at")
    search_fields = ("nom", "code", "chef_lieu")
    list_filter = ("active",)
    ordering = ("nom",)


@admin.register(Ville)
class VilleAdmin(admin.ModelAdmin):
    list_display = ("nom", "province", "code", "active", "updated_at")
    search_fields = ("nom", "province", "code")
    list_filter = ("active",)
    ordering = ("nom",)


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ("nom", "ville", "province", "code", "active", "updated_at")
    search_fields = ("nom", "ville", "province", "code")
    list_filter = ("active",)
    ordering = ("nom",)
