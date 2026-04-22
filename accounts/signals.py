from django.contrib.auth import get_user_model
from django.conf import settings
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


@receiver(post_migrate)
def ensure_hotel_de_ville_superadmin(sender, **kwargs):
    """
    Crée automatiquement le compte Hôtel de ville (ADMIN) au premier lancement,
    si aucun compte équivalent n'existe déjà.
    """

    # Ne s'exécute que quand l'app accounts migre
    if getattr(sender, "name", None) != "accounts":
        return

    username = getattr(settings, "HDV_ADMIN_USERNAME", "hoteldeville")
    email = getattr(settings, "HDV_ADMIN_EMAIL", "hoteldeville@muniworks.local")
    password = getattr(settings, "HDV_ADMIN_PASSWORD", "hoteldeville123")

    user = User.objects.filter(username=username).first() or User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name="Hôtel",
            last_name="de ville",
            is_active=True,
        )
    # Super-admin Django (admin site + toutes permissions)
    changed = False
    if not getattr(user, "is_staff", False):
        user.is_staff = True
        changed = True
    if not getattr(user, "is_superuser", False):
        user.is_superuser = True
        changed = True
    if changed:
        user.save(update_fields=["is_staff", "is_superuser"])
    # profil + rôle
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = UserProfile.objects.create(user=user)
    if profile.role != UserRole.ADMIN:
        profile.role = UserRole.ADMIN
        profile.email_verified = True
        profile.save(update_fields=["role", "email_verified"])

