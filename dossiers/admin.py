from django.contrib import admin

from dossiers.models import Demande, Document, GalleryPhoto


@admin.register(Demande)
class DemandeAdmin(admin.ModelAdmin):
    list_display = ("reference", "citoyen", "type_demande", "statut", "updated_at")
    list_select_related = ("citoyen",)
    list_filter = ("statut",)
    search_fields = ("type_demande", "declarant_nom", "citoyen__username", "citoyen__email")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-updated_at",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("titre", "demande", "citoyen", "created_at")
    list_select_related = ("demande", "demande__citoyen")
    search_fields = ("titre", "demande__type_demande", "demande__citoyen__username", "demande__citoyen__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(ordering="demande__citoyen__username", description="Citoyen")
    def citoyen(self, obj: Document):
        return obj.demande.citoyen


@admin.register(GalleryPhoto)
class GalleryPhotoAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "sort_order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "description")
    ordering = ("sort_order", "-created_at")
