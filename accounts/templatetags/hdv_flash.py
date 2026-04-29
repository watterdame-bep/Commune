"""Tags template pour l’espace HDV (messages flash dédupliqués)."""

from __future__ import annotations

from django import template
from django.contrib import messages

register = template.Library()


@register.inclusion_tag("includes/hdv_flash_messages.html", takes_context=True)
def hdv_flash_messages(context):
    """
    Consomme les messages Django une seule fois et n’affiche qu’une entrée par
    couple (niveau, texte) pour éviter les doublons (double POST, retours, etc.).
    """
    request = context.get("request")
    if request is None:
        return {"messages": []}
    raw = list(messages.get_messages(request))
    seen: set[tuple[int, str]] = set()
    deduped = []
    for m in raw:
        key = (int(m.level), str(m.message).strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)
    return {"messages": deduped}
