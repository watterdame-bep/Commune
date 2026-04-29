from django.db import models

from referentiel_geo.models import Commune


class TaxType(models.TextChoices):
    IPM = "ipm", "IPM"
    IRL = "irl", "IRL"
    ETALAGE = "etalage", "Taxe d’étalage"


class PaymentChannel(models.TextChoices):
    CASH = "cash", "Cash"
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    BANK = "bank", "Banque"


class PaymentStatus(models.TextChoices):
    SUCCEEDED = "succeeded", "Réussi"
    FAILED = "failed", "Échoué"
    CANCELLED = "cancelled", "Annulé"


class CommuneTaxPayment(models.Model):
    """Paiement fiscal agrégé au niveau commune (pas de données nominatives)."""

    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name="tax_payments", db_constraint=False)
    tax_type = models.CharField(max_length=24, choices=TaxType.choices, db_index=True)
    channel = models.CharField(max_length=24, choices=PaymentChannel.choices, db_index=True)
    status = models.CharField(max_length=24, choices=PaymentStatus.choices, default=PaymentStatus.SUCCEEDED, db_index=True)
    amount_cdf = models.PositiveIntegerField(default=0)
    paid_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_communetaxpayment"
        indexes = [
            models.Index(fields=["commune", "tax_type", "paid_at"]),
            models.Index(fields=["commune", "channel", "paid_at"]),
        ]
        ordering = ("-paid_at",)

    def __str__(self) -> str:
        return f"{self.commune_id}:{self.tax_type}:{self.amount_cdf}"


class IncidentSeverity(models.TextChoices):
    LOW = "low", "Faible"
    MEDIUM = "medium", "Moyenne"
    HIGH = "high", "Élevée"
    CRITICAL = "critical", "Critique"


class IncidentType(models.TextChoices):
    PUBLIC_ORDER = "public_order", "Ordre public"
    CRIME = "crime", "Criminalité"
    DISASTER = "disaster", "Catastrophe"
    OTHER = "other", "Autre"


class SecurityIncident(models.Model):
    """Incidents sécuritaires / mains courantes — sans détails personnels."""

    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name="incidents", db_constraint=False)
    incident_type = models.CharField(max_length=32, choices=IncidentType.choices, db_index=True)
    severity = models.CharField(max_length=24, choices=IncidentSeverity.choices, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_securityincident"
        indexes = [
            models.Index(fields=["commune", "occurred_at"]),
            models.Index(fields=["commune", "incident_type", "occurred_at"]),
        ]
        ordering = ("-occurred_at",)

    def __str__(self) -> str:
        return f"inc:{self.commune_id}:{self.incident_type}:{self.severity}"


class RiskType(models.TextChoices):
    EROSION = "erosion", "Érosion"
    FLOOD = "flood", "Inondation"
    LANDSLIDE = "landslide", "Glissement"
    OTHER = "other", "Autre"


class RiskLevel(models.TextChoices):
    LOW = "low", "Faible"
    MEDIUM = "medium", "Moyen"
    HIGH = "high", "Élevé"


class RiskZone(models.Model):
    """Zone à risque (F22) — agrégée au niveau commune (pas d’adresses privées)."""

    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name="risk_zones", db_constraint=False)
    risk_type = models.CharField(max_length=24, choices=RiskType.choices, db_index=True)
    level = models.CharField(max_length=16, choices=RiskLevel.choices, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    identified_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_riskzone"
        indexes = [
            models.Index(fields=["commune", "risk_type", "identified_at"]),
        ]
        ordering = ("-identified_at",)

    def __str__(self) -> str:
        return f"risk:{self.commune_id}:{self.risk_type}:{self.level}"


class LegalEntityType(models.TextChoices):
    ASBL = "asbl", "ASBL"
    CHURCH = "church", "Église"


class LegalEntity(models.Model):
    """Répertoire ASBL/Églises (F21) — sans données sensibles."""

    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name="legal_entities", db_constraint=False)
    entity_type = models.CharField(max_length=16, choices=LegalEntityType.choices, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_legalentity"
        indexes = [
            models.Index(fields=["commune", "entity_type", "created_at"]),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"entity:{self.commune_id}:{self.entity_type}"
