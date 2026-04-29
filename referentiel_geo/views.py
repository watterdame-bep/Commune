from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Case, Count, IntegerField, Q, When
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.http import JsonResponse

from accounts.models import Province, UserRole, Ville
from referentiel_geo.models import Commune

import re
import os
import json
from urllib.request import Request, urlopen


def _require_ministere_role(request):
    """Accès Ministère : supervision nationale (SUPER_ADMIN) uniquement."""
    if not request.user.is_authenticated:
        return redirect("login")
    if getattr(request.user, "is_superuser", False):
        return None
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role != UserRole.SUPER_ADMIN:
        messages.error(request, "Accès refusé.", extra_tags="ministere")
        return redirect("dashboard")
    return None


@login_required
@require_http_methods(["GET"])
def ministere_provinces_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    q = (request.GET.get("q") or "").strip()

    qs = Province.objects.all().order_by("nom")
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q) | Q(chef_lieu__icontains=q))

    def is_initialized(p: Province) -> bool:
        return bool(
            (p.chef_lieu or "").strip()
            and p.latitude is not None
            and p.longitude is not None
            and p.superficie_km2 is not None
            and p.population_estimee is not None
        )

    prov_list = list(qs[:500])
    all_initialized = bool(prov_list) and all(is_initialized(p) for p in prov_list)

    stats = Province.objects.aggregate(
        total=Count("id"),
        active_count=models.Sum(Case(When(Q(active=True), then=1), default=0, output_field=IntegerField())),
        inactive_count=models.Sum(Case(When(Q(active=False), then=1), default=0, output_field=IntegerField())),
        population=models.Sum("population_estimee"),
        superficie=models.Sum("superficie_km2"),
        territoires=models.Sum("nb_territoires"),
        villes=models.Sum("nb_villes"),
    )

    ctx = {
        "current": "ministere_provinces",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
        "q": q,
        "stats": {
            "total": int(stats.get("total") or 0),
            "active": int(stats.get("active_count") or 0),
            "inactive": int(stats.get("inactive_count") or 0),
            "population": int(stats.get("population") or 0),
            "superficie": stats.get("superficie") or Decimal("0"),
            "territoires": int(stats.get("territoires") or 0),
            "villes": int(stats.get("villes") or 0),
        },
        "provinces": prov_list,
        "all_initialized": all_initialized,
    }
    return render(request, "ministere_provinces.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def ministere_province_create_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    def as_int(raw: str | None):
        s = (raw or "").strip()
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def as_decimal(raw: str | None):
        s = (raw or "").strip().replace(",", ".")
        if s == "":
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None

    villes_all = Ville.objects.all().order_by("nom")[:1000]

    if request.method == "POST":
        nom = (request.POST.get("nom") or "").strip()
        code = (request.POST.get("code") or "").strip()
        active = request.POST.get("active") == "on"

        lat = as_decimal(request.POST.get("latitude"))
        lng = as_decimal(request.POST.get("longitude"))
        limites = (request.POST.get("limites_voisines") or "").strip()
        superficie = as_decimal(request.POST.get("superficie_km2"))

        population = as_int(request.POST.get("population_estimee"))
        nb_territoires = as_int(request.POST.get("nb_territoires"))
        villes_ids_raw = request.POST.getlist("villes_ids")
        villes_ids: list[int] = []
        for raw in villes_ids_raw:
            try:
                villes_ids.append(int(str(raw)))
            except ValueError:
                continue
        villes_ids = sorted(set(villes_ids))
        nb_villes = len(villes_ids) if villes_ids else None

        ressources = (request.POST.get("ressources_principales") or "").strip()
        chef_lieu_ville_id = (request.POST.get("chef_lieu_ville_id") or "").strip()
        chef_lieu = ""
        if chef_lieu_ville_id:
            try:
                chef_lieu_id = int(chef_lieu_ville_id)
            except ValueError:
                chef_lieu_id = None
            if chef_lieu_id is not None:
                if villes_ids and chef_lieu_id not in villes_ids:
                    messages.error(
                        request,
                        "Le chef-lieu doit faire partie des villes rattachées sélectionnées.",
                        extra_tags="ministere",
                    )
                    return redirect("ministere_province_create")
                v = Ville.objects.filter(pk=chef_lieu_id).first()
                chef_lieu = (v.nom if v else "") or ""

        if len(nom) < 2:
            messages.error(request, "Nom de province requis.", extra_tags="ministere")
            return redirect("ministere_province_create")
        if Province.objects.filter(nom__iexact=nom).exists():
            messages.error(request, "Cette province existe déjà.", extra_tags="ministere")
            return redirect("ministere_province_create")

        prov = Province.objects.create(
            nom=nom,
            code=code,
            chef_lieu=chef_lieu,
            latitude=lat,
            longitude=lng,
            limites_voisines=limites,
            superficie_km2=superficie,
            population_estimee=population,
            nb_territoires=nb_territoires,
            nb_villes=nb_villes,
            ressources_principales=ressources,
            active=active,
        )
        if villes_ids:
            Ville.objects.filter(pk__in=villes_ids).update(province=prov.nom)
        messages.success(request, "Province créée.", extra_tags="ministere")
        return redirect("ministere_provinces")

    ctx = {
        "current": "ministere_province_create",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
        "villes": villes_all,
    }
    return render(request, "ministere_province_create.html", ctx)


@login_required
@require_http_methods(["GET"])
def ministere_province_name_exists_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied
    nom = (request.GET.get("nom") or "").strip()
    exists = False
    if len(nom) >= 2:
        exists = Province.objects.filter(nom__iexact=nom).exists()
    return JsonResponse({"exists": bool(exists)})


@login_required
@require_http_methods(["POST"])
def ministere_provinces_initialize_all_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    # 1) Crée les provinces manquantes depuis le GeoJSON local (noms fiables)
    try:
        from django.conf import settings

        geo_path = os.path.join(settings.BASE_DIR, "static", "geo", "cod_provinces.geojson")
        with open(geo_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        names: set[str] = set()
        for feat in (data.get("features") or []):
            p = (feat.get("properties") or {})
            n = (p.get("shapeName") or p.get("shapeNAME") or p.get("NAME_1") or p.get("name") or p.get("Name") or "").strip()
            if n:
                names.add(n)
        for name in sorted(names):
            Province.objects.get_or_create(nom=name, defaults={"active": True})
    except Exception:
        # Sans geojson, on continue: on initialise au moins les provinces existantes
        pass

    # 2) Initialise les champs clés via sources publiques (best effort)
    def is_initialized(p: Province) -> bool:
        return bool(
            (p.chef_lieu or "").strip()
            and p.latitude is not None
            and p.longitude is not None
            and p.superficie_km2 is not None
            and p.population_estimee is not None
        )

    updated = 0
    for prov in Province.objects.all().order_by("nom"):
        if is_initialized(prov):
            continue
        seed = _fetch_seed_from_web(prov.nom)
        if not seed:
            continue

        chef_lieu = str(seed.get("chef_lieu") or "").strip()
        superficie = seed.get("superficie_km2")
        population = seed.get("population_estimee")
        lat = str(seed.get("latitude") or "").strip()
        lng = str(seed.get("longitude") or "").strip()

        changed = False
        if chef_lieu:
            prov.chef_lieu = chef_lieu
            changed = True
        if isinstance(superficie, int) and superficie > 0:
            prov.superficie_km2 = superficie
            changed = True
        if isinstance(population, int) and population > 0:
            prov.population_estimee = population
            changed = True
        if lat:
            prov.latitude = lat
            changed = True
        if lng:
            prov.longitude = lng
            changed = True
        if changed:
            prov.active = True
            try:
                prov.save()
                updated += 1
            except Exception:
                continue

        # Ville chef-lieu
        if chef_lieu:
            v = Ville.objects.filter(nom__iexact=chef_lieu).first()
            if v is None:
                try:
                    v = Ville.objects.create(nom=chef_lieu, province=prov.nom, code="", active=True)
                except Exception:
                    v = None
            if v is not None and (v.province or "") != prov.nom:
                try:
                    v.province = prov.nom
                    v.save(update_fields=["province"])
                except Exception:
                    pass

            # Commune minimale chef-lieu
            try:
                if not Commune.objects.filter(nom__iexact=chef_lieu, province__iexact=prov.nom).exists():
                    Commune.objects.create(
                        nom=chef_lieu,
                        province=prov.nom,
                        code="",
                        active=True,
                        ville=chef_lieu,
                    )
            except Exception:
                pass

    if updated:
        messages.success(request, f"Initialisation terminée : {updated} province(s) mises à jour.", extra_tags="ministere")
    else:
        messages.info(request, "Toutes les provinces semblent déjà initialisées (ou aucune donnée récupérable).", extra_tags="ministere")
    return redirect("ministere_provinces")


@login_required
@require_http_methods(["GET", "POST"])
def ministere_province_edit_view(request, pk: int):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    prov = Province.objects.filter(pk=pk).first()
    if prov is None:
        messages.error(request, "Province introuvable.", extra_tags="ministere")
        return redirect("ministere_provinces")

    villes_all = Ville.objects.all().order_by("nom")[:1500]
    selected_villes = set(str(x) for x in Ville.objects.filter(province=prov.nom).values_list("pk", flat=True))

    def as_int(raw: str | None):
        s = (raw or "").strip()
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def as_decimal(raw: str | None):
        s = (raw or "").strip().replace(",", ".")
        if s == "":
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        active = request.POST.get("active") == "on"
        lat = as_decimal(request.POST.get("latitude"))
        lng = as_decimal(request.POST.get("longitude"))
        limites = (request.POST.get("limites_voisines") or "").strip()
        superficie = as_decimal(request.POST.get("superficie_km2"))
        population = as_int(request.POST.get("population_estimee"))
        nb_territoires = as_int(request.POST.get("nb_territoires"))
        ressources = (request.POST.get("ressources_principales") or "").strip()

        villes_ids_raw = request.POST.getlist("villes_ids")
        villes_ids: list[int] = []
        for raw in villes_ids_raw:
            try:
                villes_ids.append(int(str(raw)))
            except ValueError:
                continue
        villes_ids = sorted(set(villes_ids))

        chef_lieu_ville_id = (request.POST.get("chef_lieu_ville_id") or "").strip()
        chef_lieu = ""
        if chef_lieu_ville_id:
            try:
                chef_lieu_id = int(chef_lieu_ville_id)
            except ValueError:
                chef_lieu_id = None
            if chef_lieu_id is not None:
                if villes_ids and chef_lieu_id not in villes_ids:
                    messages.error(
                        request,
                        "Le chef-lieu doit faire partie des villes rattachées sélectionnées.",
                        extra_tags="ministere",
                    )
                    return redirect("ministere_province_edit", pk=pk)
                v = Ville.objects.filter(pk=chef_lieu_id).first()
                chef_lieu = (v.nom if v else "") or ""

        prov.code = code
        prov.chef_lieu = chef_lieu or (prov.chef_lieu or "")
        prov.latitude = lat
        prov.longitude = lng
        prov.limites_voisines = limites
        prov.superficie_km2 = superficie
        prov.population_estimee = population
        prov.nb_territoires = nb_territoires
        prov.nb_villes = len(villes_ids) if villes_ids else None
        prov.ressources_principales = ressources
        prov.active = active
        prov.save()

        wanted = set(villes_ids)
        current = set(Ville.objects.filter(province=prov.nom).values_list("pk", flat=True))
        to_add = wanted - current
        to_remove = current - wanted
        if to_add:
            Ville.objects.filter(pk__in=to_add).update(province=prov.nom)
        if to_remove:
            Ville.objects.filter(pk__in=to_remove).update(province="")

        messages.success(request, "Province mise à jour.", extra_tags="ministere")
        return redirect("ministere_provinces")

    ctx = {
        "current": "ministere_provinces",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
        "province": prov,
        "villes": villes_all,
        "selected_villes": selected_villes,
    }
    return render(request, "ministere_province_edit.html", ctx)


@login_required
@require_http_methods(["POST"])
def ministere_province_delete_view(request, pk: int):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    prov = Province.objects.filter(pk=pk).first()
    if prov is None:
        messages.error(request, "Province introuvable.", extra_tags="ministere")
        return redirect("ministere_provinces")

    try:
        Ville.objects.filter(province=prov.nom).update(province="")
    except Exception:
        pass

    prov.delete()
    messages.success(request, "Province supprimée.", extra_tags="ministere")
    return redirect("ministere_provinces")


@login_required
def ministere_geo_villes_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied
    return redirect("ministere_villes")


@login_required
def ministere_geo_communes_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied
    ctx = {
        "current": "ministere_geo_communes",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
    }
    return render(request, "ministere_geo_communes.html", ctx)


@login_required
def ministere_geo_quartiers_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied
    ctx = {
        "current": "ministere_geo_quartiers",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
    }
    return render(request, "ministere_geo_quartiers.html", ctx)


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")


def _fetch_seed_from_web(province_name: str) -> dict[str, object] | None:
    """
    Récupère des données publiques (chef-lieu, superficie, population) depuis Wikipedia FR,
    et (lat/lng) depuis GeoKeo. Retourne None si introuvable.
    """
    key = f"seed:rdc:province:{_norm_key(province_name)}"
    cached = cache.get(key)
    if isinstance(cached, dict):
        return cached

    seed: dict[str, object] = {"nom": province_name}

    # 1) Wikipedia (chef-lieu, superficie, population) — parsing léger (best effort)
    try:
        wiki_url = "https://fr.wikipedia.org/wiki/Provinces_de_la_r%C3%A9publique_d%C3%A9mocratique_du_Congo"
        req = Request(wiki_url, headers={"User-Agent": "MuniWorksDRC/1.0"})
        html = urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        # Cherche une ligne contenant le nom de province dans une table
        # On capture chef-lieu (lien), superficie (km²) et population (est.) si présents.
        # NOTE: parsing volontairement robuste (HTML varie).
        prov_esc = re.escape(province_name)
        row_match = re.search(rf"<tr[^>]*>[\s\S]*?{prov_esc}[\s\S]*?</tr>", html, flags=re.IGNORECASE)
        if row_match:
            row = row_match.group(0)
            # Chef-lieu: premier <a> après le nom de province
            a = re.findall(r"<a[^>]*>([^<]+)</a>", row)
            if len(a) >= 2:
                seed["chef_lieu"] = re.sub(r"\s+", " ", a[1]).strip()
            # Superficie km²
            area = re.search(r"([\d\s\u202f]+)\s*(?:km²|km2)", row, flags=re.IGNORECASE)
            if area:
                seed["superficie_km2"] = int(re.sub(r"[^\d]", "", area.group(1)) or 0) or None
            # Population (nombre)
            pop = re.search(r"([\d\s\u202f]+)\s*(?:hab\.|habitants|hab)", row, flags=re.IGNORECASE)
            if pop:
                seed["population_estimee"] = int(re.sub(r"[^\d]", "", pop.group(1)) or 0) or None
    except Exception:
        pass

    # 2) GeoKeo (lat/lng) — table simple "State / Latitude / Longitude"
    try:
        geo_url = "https://geokeo.com/database/state/cd/"
        req = Request(geo_url, headers={"User-Agent": "MuniWorksDRC/1.0"})
        html = urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        prov = re.escape(province_name)
        m = re.search(
            rf">{prov}</a>\s*</td>\s*<td[^>]*>\s*([-0-9\.]+)\s*</td>\s*<td[^>]*>\s*([-0-9\.]+)\s*</td>",
            html,
            flags=re.IGNORECASE,
        )
        if m:
            seed["latitude"] = m.group(1)
            seed["longitude"] = m.group(2)
    except Exception:
        pass

    # Minimum utile : si rien de récupéré, on abandonne
    useful = any(k in seed for k in ("chef_lieu", "superficie_km2", "population_estimee", "latitude", "longitude"))
    if not useful:
        return None

    cache.set(key, seed, timeout=60 * 60 * 24 * 7)  # 7 jours
    return seed


@login_required
@require_http_methods(["POST"])
def ministere_province_initialize_view(request, pk: int):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    prov = Province.objects.filter(pk=pk).first()
    if prov is None:
        messages.error(request, "Province introuvable.", extra_tags="ministere")
        return redirect("ministere_provinces")

    seed = _fetch_seed_from_web(prov.nom)
    if not seed:
        messages.error(request, "Impossible de récupérer les données publiques pour cette province.", extra_tags="ministere")
        return redirect("ministere_provinces")

    # Mise à jour des champs clés (on écrase pour garantir la cohérence “vraie”)
    chef_lieu = str(seed.get("chef_lieu") or "").strip()
    superficie = seed.get("superficie_km2")
    population = seed.get("population_estimee")
    lat = str(seed.get("latitude") or "").strip()
    lng = str(seed.get("longitude") or "").strip()

    try:
        prov.chef_lieu = chef_lieu or (prov.chef_lieu or "")
        if isinstance(superficie, int) and superficie > 0:
            prov.superficie_km2 = superficie
        if isinstance(population, int) and population > 0:
            prov.population_estimee = population
        if lat:
            prov.latitude = lat
        if lng:
            prov.longitude = lng
        prov.active = True
        prov.save()
    except Exception:
        messages.error(request, "Échec de mise à jour de la province.", extra_tags="ministere")
        return redirect("ministere_provinces")

    # Crée (ou met à jour) la ville chef-lieu si besoin
    if chef_lieu:
        v = Ville.objects.filter(nom__iexact=chef_lieu).first()
        if v is None:
            try:
                v = Ville.objects.create(nom=chef_lieu, province=prov.nom, code="", active=True)
            except Exception:
                v = None
        if v is not None and (v.province or "") != prov.nom:
            try:
                v.province = prov.nom
                v.save(update_fields=["province"])
            except Exception:
                pass

        # Crée une entrée Commune minimale (données fines complétées plus tard)
        # Objectif : rendre le registre navigable immédiatement.
        try:
            if not Commune.objects.filter(nom__iexact=chef_lieu, province__iexact=prov.nom).exists():
                Commune.objects.create(
                    nom=chef_lieu,
                    province=prov.nom,
                    code="",
                    active=True,
                    ville=chef_lieu,
                )
        except Exception:
            pass

    messages.success(request, "Province initialisée (données clés + chef-lieu).", extra_tags="ministere")
    return redirect("ministere_provinces")
