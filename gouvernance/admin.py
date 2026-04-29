from django.contrib import admin

from gouvernance.models import CommuneTaxPayment, LegalEntity, RiskZone, SecurityIncident


@admin.register(CommuneTaxPayment)
class CommuneTaxPaymentAdmin(admin.ModelAdmin):
    list_display = ("commune", "tax_type", "channel", "status", "amount_cdf", "paid_at")
    list_filter = ("tax_type", "channel", "status")
    search_fields = ("commune__nom",)
    ordering = ("-paid_at",)


@admin.register(SecurityIncident)
class SecurityIncidentAdmin(admin.ModelAdmin):
    list_display = ("commune", "incident_type", "severity", "is_verified", "occurred_at")
    list_filter = ("incident_type", "severity", "is_verified")
    search_fields = ("commune__nom",)
    ordering = ("-occurred_at",)


@admin.register(RiskZone)
class RiskZoneAdmin(admin.ModelAdmin):
    list_display = ("commune", "risk_type", "level", "is_active", "identified_at")
    list_filter = ("risk_type", "level", "is_active")
    search_fields = ("commune__nom",)
    ordering = ("-identified_at",)


@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ("commune", "entity_type", "is_active", "created_at")
    list_filter = ("entity_type", "is_active")
    search_fields = ("commune__nom",)
    ordering = ("-created_at",)
