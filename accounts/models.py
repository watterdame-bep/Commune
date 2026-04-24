from django.conf import settings
from django.db import models


class UserRole(models.TextChoices):
    CITOYEN = "citoyen", "Citoyen"
    AGENT = "agent", "Agent"
    CHEF_SERVICE = "chef_service", "Chef de service"
    ADMIN = "admin", "Admin"


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=UserRole.choices, default=UserRole.CITOYEN)
    email_verified = models.BooleanField(default=False)
    profession = models.CharField(max_length=120, blank=True, default="")

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"


class DemandeStatut(models.TextChoices):
    BROUILLON = "brouillon", "Brouillon"
    EN_EXAMEN = "en_examen", "En examen"
    APPROUVE = "approuve", "Approuvé"
    ACTION_REQUISE = "action_requise", "Action requise"
    REJETE = "rejete", "Rejeté"


class Demande(models.Model):
    """Dossier / demande administrative rattachée à un citoyen."""

    citoyen = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="demandes",
    )
    type_demande = models.CharField(max_length=200)
    statut = models.CharField(
        max_length=32,
        choices=DemandeStatut.choices,
        default=DemandeStatut.BROUILLON,
        db_index=True,
    )
    declarant_nom = models.CharField("Nom et prénom(s)", max_length=200, blank=True, default="")
    declarant_telephone = models.CharField("Téléphone", max_length=40, blank=True, default="")
    declarant_email = models.CharField("Email de contact", max_length=254, blank=True, default="")
    declarant_adresse = models.TextField("Adresse complète", blank=True, default="")
    motif_precisions = models.TextField("Motif et précisions", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.reference} — {self.citoyen_id}"

    @property
    def reference(self) -> str:
        if self.pk is None:
            return "#RDC—nouveau"
        year = self.created_at.year
        return f"#RDC-{year}-{self.pk:06d}"


class Document(models.Model):
    """Document délivré suite à une demande (téléchargeable par le citoyen)."""

    demande = models.ForeignKey(Demande, on_delete=models.CASCADE, related_name="documents")
    titre = models.CharField(max_length=200)
    fichier = models.FileField(upload_to="documents/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.titre} ({self.demande_id})"


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


class Commune(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    province = models.CharField(max_length=120, blank=True, default="")
    code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nom",)

    def __str__(self) -> str:
        return self.nom

