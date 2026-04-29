from django.conf import settings
from django.db import models

from dossiers.models import Demande, DemandeStatut, Document, GalleryPhoto
from gouvernance.models import (
    CommuneTaxPayment,
    IncidentSeverity,
    IncidentType,
    LegalEntity,
    LegalEntityType,
    PaymentChannel,
    PaymentStatus,
    RiskLevel,
    RiskType,
    RiskZone,
    SecurityIncident,
    TaxType,
)
from referentiel_geo.models import Commune, Province, Ville


class UserRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super-admin (Ministère)"
    CITY_ADMIN = "city_admin", "Admin ville (Hôtel de ville)"
    COMMUNE_ADMIN = "commune_admin", "Admin commune (Bourgmestre)"
    CITOYEN = "citoyen", "Citoyen"
    AGENT = "agent", "Agent"
    CHEF_SERVICE = "chef_service", "Chef de service"
    ADMIN = "admin", "Admin (legacy)"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.CITOYEN)
    email_verified = models.BooleanField(default=False)
    profession = models.CharField(max_length=120, blank=True, default="")
    ville = models.ForeignKey(Ville, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")
    commune = models.ForeignKey(Commune, null=True, blank=True, on_delete=models.SET_NULL, related_name="users")

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"reset:{self.user_id} exp:{self.expires_at:%Y-%m-%d %H:%M}"



