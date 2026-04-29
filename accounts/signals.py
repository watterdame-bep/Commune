from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_migrate
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile
from accounts.models import UserRole

User = get_user_model()


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


def ensure_ministere_account() -> None:
    """
    Assure l'existence du compte Ministère de l’Intérieur (SUPER_ADMIN).

    Idempotent. Peut être appelé au démarrage (si DB prête) et après migrations.
    """
    username = getattr(settings, "MINISTER_ADMIN_USERNAME", "ministere")
    email = getattr(settings, "MINISTER_ADMIN_EMAIL", "ministere@muniworks.local")
    password = getattr(settings, "MINISTER_ADMIN_PASSWORD", "ministere12345")

    user = User.objects.filter(username=username).first() or User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name="Ministère",
            last_name="Intérieur",
            is_active=True,
        )

    changed = False
    if not getattr(user, "is_staff", False):
        user.is_staff = True
        changed = True
    if not getattr(user, "is_superuser", False):
        user.is_superuser = True
        changed = True
    if changed:
        user.save(update_fields=["is_staff", "is_superuser"])

    profile = getattr(user, "profile", None)
    if profile is None:
        profile = UserProfile.objects.create(user=user)
    if profile.role != UserRole.SUPER_ADMIN:
        profile.role = UserRole.SUPER_ADMIN
        profile.email_verified = True
        profile.ville = None
        profile.commune = None
        profile.save(update_fields=["role", "email_verified", "ville", "commune"])


@receiver(post_migrate)
def ensure_ministere_superadmin(sender, **kwargs):
    """
    Crée automatiquement le compte Ministère de l’Intérieur (SUPER_ADMIN) au premier lancement,
    si aucun compte équivalent n'existe déjà.
    """

    # Ne s'exécute que quand l'app accounts migre
    if getattr(sender, "name", None) != "accounts":
        return

    try:
        ensure_ministere_account()
    except (OperationalError, ProgrammingError):
        # DB pas prête / tables pas encore créées
        return

