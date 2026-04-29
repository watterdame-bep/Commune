from django.apps import AppConfig
import sys
import os


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from . import signals  # noqa: F401

        # Création automatique du compte Ministère au lancement (si DB prête).
        # Idempotent ; ignore si DB non migrée.
        try:
            if any(arg in {"runserver", "gunicorn", "uvicorn"} for arg in sys.argv):
                signals.ensure_ministere_account()
        except Exception:
            return

        # Création automatique du compte Ministère au lancement (si DB prête).
        # Ne pas échouer si les tables ne sont pas encore créées.
        try:
            if any(arg in {"runserver", "gunicorn", "uvicorn"} for arg in os.sys.argv):
                signals.ensure_ministere_account()
        except Exception:
            # DB pas prête (migrations non appliquées) ou autre erreur non critique au démarrage.
            return

