from __future__ import annotations

from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from dossiers.models import GalleryPhoto


class Command(BaseCommand):
    help = "Crée 5 photos de galerie (seed) depuis images/commune-image/."

    def handle(self, *args, **options):
        base = Path.cwd()
        src_dir = base / "images" / "commune-image"
        if not src_dir.exists():
            self.stderr.write(self.style.ERROR(f"Dossier introuvable: {src_dir}"))
            return

        # Priorité à ces images (celles utilisées historiquement par le carrousel).
        preferred = [
            "comune1.png",
            "comune2.png",
            "commune3.png",
            "commune4.png",
            "commune5.jpg",
        ]

        paths: list[Path] = []
        for name in preferred:
            p = src_dir / name
            if p.exists():
                paths.append(p)

        if len(paths) < 5:
            # Compléter si certaines manquent.
            for p in sorted(src_dir.iterdir()):
                if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and p not in paths:
                    paths.append(p)
                if len(paths) >= 5:
                    break

        if len(paths) < 5:
            self.stderr.write(self.style.ERROR("Pas assez d'images trouvées (minimum 5)."))
            return

        samples = [
            {
                "title": "Accueil de la maison communale",
                "description": (
                    "Déposez vos demandes, suivez chaque étape et récupérez vos documents sans file d’attente. "
                    "Une plateforme sécurisée pour l’état civil, les autorisations communales et l’archivage. "
                    "L’Hôtel de ville supervise et pilote l’activité globale."
                ),
            },
            {
                "title": "Services municipaux en ligne",
                "description": (
                    "Accédez aux services communaux depuis votre téléphone ou votre ordinateur. "
                    "Chaque dossier est tracé, chaque étape est notifiée, et les délais sont visibles. "
                    "Une modernisation concrète de l’administration."
                ),
            },
            {
                "title": "Transparence & suivi",
                "description": (
                    "Un suivi clair des demandes pour réduire les déplacements et améliorer la transparence. "
                    "Les communes exécutent, l’Hôtel de ville contrôle, analyse et décide à partir des statistiques."
                ),
            },
            {
                "title": "Sécurité & gouvernance",
                "description": (
                    "Des accès maîtrisés, des rôles définis, et des indicateurs de performance. "
                    "Le portail structure la gouvernance numérique et renforce la qualité du service public."
                ),
            },
            {
                "title": "Une ville connectée",
                "description": (
                    "Cartographie, référentiel géographique, localisation des maisons communales : "
                    "la base pour évoluer vers une approche smart city. "
                    "Des données fiables pour mieux planifier et mieux servir."
                ),
            },
        ]

        # Libérer les positions 0..4 pour les 5 éléments seed (sans supprimer).
        for i in range(5):
            for other in GalleryPhoto.objects.filter(sort_order=i).exclude(title__in=[s["title"] for s in samples]):
                other.sort_order = 50 + other.pk
                other.save(update_fields=["sort_order"])

        created = 0
        updated = 0
        for i, p in enumerate(paths[:5]):
            meta = samples[i]
            obj = GalleryPhoto.objects.filter(title=meta["title"]).first()
            if obj is None:
                with p.open("rb") as f:
                    GalleryPhoto.objects.create(
                        image=File(f, name=p.name),
                        title=meta["title"],
                        description=meta["description"],
                        is_active=True,
                        sort_order=i,
                    )
                created += 1
            else:
                obj.description = meta["description"]
                obj.is_active = True
                obj.sort_order = i
                # Ne remplace l'image que si vide (cas rare)
                if not getattr(obj, "image", None):
                    with p.open("rb") as f:
                        obj.image = File(f, name=p.name)
                obj.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Seed galerie: {created} créée(s), {updated} mise(s) à jour."))

