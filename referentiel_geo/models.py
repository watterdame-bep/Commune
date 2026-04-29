from django.db import models


class Province(models.Model):
    """Province RDC — référentiel national (Ministère)."""

    nom = models.CharField(max_length=140, unique=True)
    code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    chef_lieu = models.CharField(max_length=140, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    limites_voisines = models.TextField(blank=True, default="")
    superficie_km2 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    population_estimee = models.PositiveIntegerField(null=True, blank=True)
    nb_territoires = models.PositiveIntegerField(null=True, blank=True)
    nb_villes = models.PositiveIntegerField(null=True, blank=True)
    ressources_principales = models.TextField(blank=True, default="")
    recettes_prevues_cdf = models.PositiveIntegerField(null=True, blank=True)
    etat_batiments_admin = models.TextField(blank=True, default="")
    reseau_routier = models.TextField(blank=True, default="")
    desserte_agricole = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "accounts_province"
        ordering = ("nom",)

    def __str__(self) -> str:
        return self.nom


class Ville(models.Model):
    """Ville / entité urbaine créée par le niveau national (Ministère)."""

    nom = models.CharField(max_length=140, unique=True)
    province = models.CharField(max_length=120, blank=True, default="")
    code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "accounts_ville"
        ordering = ("nom",)

    def __str__(self) -> str:
        return self.nom


class Commune(models.Model):
    nom = models.CharField(max_length=120)
    province = models.CharField(max_length=120, blank=True, default="")
    code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    active = models.BooleanField(default=True)

    # Maison communale (infos de localisation)
    adresse = models.TextField("Adresse", blank=True, default="")
    quartier = models.CharField(max_length=120, blank=True, default="")
    ville = models.CharField(max_length=120, blank=True, default="")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    services_estimes = models.PositiveIntegerField(null=True, blank=True)
    population_estimee = models.PositiveIntegerField(null=True, blank=True)
    nombre_quartiers = models.PositiveIntegerField(null=True, blank=True)
    langue_defaut = models.CharField(max_length=32, blank=True, default="fr")
    fuseau_horaire = models.CharField(max_length=64, blank=True, default="Africa/Kinshasa")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "accounts_commune"
        ordering = ("nom",)

    def __str__(self) -> str:
        return self.nom
