"""Middlewares projet (messages, sécurité navigation, etc.)."""

from __future__ import annotations

from django.contrib import messages


def _path_is_sensitive_html(path: str) -> bool:
    """Chemins où une page HTML ne doit pas être mise en cache (formulaires, données personnelles)."""
    if path.startswith("/hdv/"):
        return True
    if path.startswith("/dashboard"):
        return True
    if path.startswith("/documents"):
        return True
    if path.startswith("/demandes"):
        return True
    if path.startswith("/login"):
        return True
    if path.startswith("/logout"):
        return True
    if path.startswith("/register"):
        return True
    if path.startswith("/password-reset"):
        return True
    return False


class SensitiveHtmlNoCacheMiddleware:
    """
    En-têtes Cache-Control sur les réponses HTML sensibles pour limiter
    la réutilisation de formulaires (CSRF, données post-login) depuis le cache navigateur.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path or "/"
        if not _path_is_sensitive_html(path):
            return response
        ctype = (response.get("Content-Type") or "").lower()
        if "text/html" not in ctype:
            return response
        existing = (response.get("Cache-Control") or "").lower()
        if "no-store" in existing or "no-cache" in existing:
            return response
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
        if "Pragma" not in response:
            response["Pragma"] = "no-cache"
        return response


class StripPublicAuthMessagesForHdvMiddleware:
    """
    Les messages d’authentification / inscription (tag `public_auth`) ne doivent pas
    s’afficher dans l’espace HDV : ils restent en session jusqu’à consommation, ce qui
    provoquait des listes d’alertes incohérentes sur /hdv/*.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/hdv/"):
            kept: list[tuple[int, str, str]] = []
            for m in messages.get_messages(request):
                tags = str(getattr(m, "tags", "") or "")
                if "public_auth" in tags:
                    continue
                extra = str(getattr(m, "extra_tags", "") or "")
                kept.append((int(m.level), str(m.message), extra))
            for level, msg, extra in kept:
                if extra.strip():
                    messages.add_message(request, level, msg, extra_tags=extra.strip())
                else:
                    messages.add_message(request, level, msg)
        return self.get_response(request)
