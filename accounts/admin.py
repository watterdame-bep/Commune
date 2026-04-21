from django.contrib import admin

from accounts.models import Demande, Document, PasswordResetCode, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "email_verified", "profession")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    list_filter = ("role", "email_verified")


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


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "used_at", "created_at")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email")
    list_filter = ("used_at",)
    ordering = ("-created_at",)

