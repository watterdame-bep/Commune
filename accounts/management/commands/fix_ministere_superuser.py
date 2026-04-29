from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserProfile, UserRole


class Command(BaseCommand):
    help = "Met à jour le superuser existant pour qu’il représente le Ministère (SUPER_ADMIN)."

    def handle(self, *args, **options):
        User = get_user_model()

        username = getattr(settings, "MINISTER_ADMIN_USERNAME", "ministere")
        email = getattr(settings, "MINISTER_ADMIN_EMAIL", "ministere@muniworks.local")

        user = User.objects.filter(username=username).first() or User.objects.filter(email=email).first()
        if user is None:
            # Fallback : premier superuser
            user = User.objects.filter(is_superuser=True).order_by("id").first()
        if user is None:
            self.stdout.write(self.style.WARNING("Aucun superuser trouvé."))
            return

        changed_user = False
        if not user.is_active:
            user.is_active = True
            changed_user = True
        if not user.is_staff:
            user.is_staff = True
            changed_user = True
        if not user.is_superuser:
            user.is_superuser = True
            changed_user = True
        if changed_user:
            user.save(update_fields=["is_active", "is_staff", "is_superuser"])

        profile = getattr(user, "profile", None)
        if profile is None:
            profile = UserProfile.objects.create(user=user)

        changed_profile = False
        if profile.role != UserRole.SUPER_ADMIN:
            profile.role = UserRole.SUPER_ADMIN
            changed_profile = True
        if not profile.email_verified:
            profile.email_verified = True
            changed_profile = True
        if profile.ville_id is not None:
            profile.ville = None
            changed_profile = True
        if profile.commune_id is not None:
            profile.commune = None
            changed_profile = True
        if changed_profile:
            profile.save(update_fields=["role", "email_verified", "ville", "commune"])

        self.stdout.write(
            self.style.SUCCESS(
                f"OK — superuser={user.username!r} mis à jour en SUPER_ADMIN (Ministère)."
            )
        )

