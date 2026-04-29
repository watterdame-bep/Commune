from django.contrib import admin

from accounts.models import PasswordResetCode, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "ville", "commune", "email_verified", "profession")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    list_filter = ("role", "email_verified")


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "used_at", "created_at")
    list_select_related = ("user",)
    search_fields = ("user__username", "user__email")
    list_filter = ("used_at",)
    ordering = ("-created_at",)



