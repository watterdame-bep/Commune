from django.conf import settings
from django.db import models

from referentiel_geo.models import Ville


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
        db_constraint=False,
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
        managed = False
        db_table = "accounts_demande"
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

    demande = models.ForeignKey(Demande, on_delete=models.CASCADE, related_name="documents", db_constraint=False)
    titre = models.CharField(max_length=200)
    fichier = models.FileField(upload_to="documents/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_document"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.titre} ({self.demande_id})"


class GalleryPhoto(models.Model):
    """Photos gérées par l’Hôtel de ville (affichage public sur la page d’accueil)."""

    ville = models.ForeignKey(
        Ville,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gallery_photos",
        db_constraint=False,
        db_column="ville_id",
    )
    image = models.ImageField(upload_to="gallery/%Y/%m/")
    title = models.CharField("Titre (court)", max_length=180, blank=True, default="")
    description = models.TextField("Texte (long)", blank=True, default="", max_length=500)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "accounts_galleryphoto"
        ordering = ("sort_order", "-created_at")

    def __str__(self) -> str:
        return self.title or f"photo-{self.pk}"
