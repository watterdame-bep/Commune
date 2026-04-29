import os

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import Q, Count, Max, Case, When, IntegerField
from django.db import models
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_control
from django.utils.crypto import salted_hmac
from django.conf import settings
import secrets
import re
from decimal import Decimal, InvalidOperation

_DEMANDE_FORM_KEYS = (
    "declarant_nom",
    "declarant_telephone",
    "declarant_email",
    "declarant_adresse",
    "motif_precisions",
)


def _demande_form_defaults(user: User) -> dict[str, str]:
    nom = ((user.get_full_name() or "").strip() or (user.first_name or "").strip() or "").strip()
    email = (user.email or "").strip()
    return {
        "declarant_nom": nom,
        "declarant_telephone": "",
        "declarant_email": email,
        "declarant_adresse": "",
        "motif_precisions": "",
    }


def _demande_form_from_post(post) -> dict[str, str]:
    return {k: (post.get(k) or "").strip() for k in _DEMANDE_FORM_KEYS}


def _validate_demande_form(data: dict[str, str]) -> list[str]:
    errs: list[str] = []
    if len(data["declarant_nom"]) < 3:
        errs.append("Indiquez votre nom et prénom(s) (au moins 3 caractères).")
    tel_digits = re.sub(r"\D+", "", data["declarant_telephone"])
    if len(tel_digits) < 8:
        errs.append("Indiquez un numéro de téléphone valide (au moins 8 chiffres).")
    if data["declarant_email"]:
        try:
            EmailValidator()(data["declarant_email"])
        except ValidationError:
            errs.append("L’adresse email de contact n’est pas valide.")
    if len(data["declarant_adresse"]) < 10:
        errs.append("L’adresse complète doit contenir au moins 10 caractères.")
    if len(data["motif_precisions"]) < 20:
        errs.append("Précisez le motif de votre demande (au moins 20 caractères).")
    return errs

from accounts.models import (
    Commune,
    CommuneTaxPayment,
    Demande,
    DemandeStatut,
    Document,
    GalleryPhoto,
    LegalEntity,
    PasswordResetCode,
    Province,
    RiskZone,
    SecurityIncident,
    UserProfile,
    UserRole,
    Ville,
    PaymentChannel,
    PaymentStatus,
    TaxType,
)

signer = TimestampSigner(salt="sisepcommune.email")


def _gallery_branding_reference_text() -> str:
    return (
        "Déposez vos demandes, suivez chaque étape et récupérez vos documents sans file d’attente. "
        "Une plateforme sécurisée pour l’état civil, les autorisations communales et l’archivage. "
        "L’Hôtel de ville supervise et pilote l’activité globale."
    )


def _gallery_description_limits() -> tuple[int, int, int]:
    """Retourne (min_required, display_limit, max_chars) pour le texte long de la galerie."""
    ref = _gallery_branding_reference_text()
    display_limit = len(ref) + 10
    min_required = display_limit + 1
    max_chars = 500
    return min_required, display_limit, max_chars


def _gallery_description_error(description: str) -> str | None:
    text = (description or "").strip()
    if not text:
        return "Le texte (long) est obligatoire."
    compact = " ".join(text.split())
    min_required, display_limit, max_chars = _gallery_description_limits()
    if len(compact) > max_chars:
        return f"Le texte (long) ne doit pas dépasser {max_chars} caractères."
    if len(compact) <= display_limit:
        return (
            "Le texte (long) doit dépasser la limite d’affichage du hero "
            f"({display_limit} caractères), tout en restant ≤ {max_chars} caractères."
        )
    if len(compact) < min_required:
        # Sécurité : normalement impossible si > display_limit et max_chars >= min_required
        return "Le texte (long) est trop court pour l’affichage dynamique sur l’accueil."
    return None


def _is_admin_user(user: User) -> bool:
    role = getattr(getattr(user, "profile", None), "role", None)
    return bool(
        getattr(user, "is_superuser", False)
        or role in {UserRole.SUPER_ADMIN, UserRole.CITY_ADMIN, UserRole.ADMIN}
    )


def _safe_next_redirect(request, candidate: str | None) -> str | None:
    """Évite les redirections ouvertes (open redirect) après connexion."""
    if not candidate:
        return None
    url = candidate.strip()
    if not url:
        return None
    allowed_hosts = {request.get_host()}
    if settings.ALLOWED_HOSTS:
        allowed_hosts |= set(settings.ALLOWED_HOSTS)
    if url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return url
    return None


def _client_ip(request) -> str:
    """
    IP client basique.
    Note: si vous êtes derrière un reverse proxy, configurez correctement les en-têtes
    (ex: Nginx/Traefik) et ne faites confiance à X-Forwarded-For que dans ce contexte.
    """
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        # Le premier est l’IP d’origine (les suivants sont les proxies)
        return xff.split(",")[0].strip() or "unknown"
    return (request.META.get("REMOTE_ADDR") or "").strip() or "unknown"


@cache_control(no_store=True, no_cache=True, must_revalidate=True, private=True)
def welcome(request):
    """Page d'accueil publique — point d'entrée du portail (landing)."""
    photos = list(GalleryPhoto.objects.filter(is_active=True).order_by("sort_order", "-created_at")[:8])
    return render(request, "welcome.html", {"gallery_photos": photos})


def public_gallery_view(request):
    photos = GalleryPhoto.objects.filter(is_active=True).order_by("sort_order", "-created_at")[:60]
    return render(request, "gallery_public.html", {"photos": photos})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('welcome')

    if request.method == "POST":
        ip = _client_ip(request)
        key = f"rl:login:{ip}"
        now = timezone.now().timestamp()
        state = cache.get(key)
        if not isinstance(state, dict):
            state = {"count": 0, "reset": now + 60}
        reset = float(state.get("reset") or 0)
        count = int(state.get("count") or 0)
        if reset <= now:
            reset = now + 60
            count = 0
        if count >= 5:
            retry_after = max(1, int(round(reset - now)))
            resp = render(
                request,
                "login.html",
                {"rate_limited": True, "retry_after": retry_after},
                status=429,
            )
            resp["Retry-After"] = str(retry_after)
            return resp
        cache.set(key, {"count": count + 1, "reset": reset}, timeout=max(1, int(round(reset - now))))

        identifier = (request.POST.get("username") or "").strip().lower()
        password = request.POST.get("password") or ""
        username = identifier
        if identifier and "@" in identifier:
            u = User.objects.filter(email__iexact=identifier).first()
            if u is not None:
                username = u.username

        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            cache.delete(key)
            raw_next = request.GET.get("next") or request.POST.get("next")
            next_url = _safe_next_redirect(request, raw_next)
            role = getattr(getattr(user, "profile", None), "role", None)
            if role == UserRole.SUPER_ADMIN:
                return redirect(next_url or "ministere_dashboard")
            if _is_admin_user(user):
                return redirect(next_url or "hdv_dashboard")
            return redirect(next_url or "dashboard")
        # Message plus clair si le compte existe mais n'est pas activé
        if identifier and User.objects.filter(email__iexact=identifier, is_active=False).exists():
            messages.error(request, "Veuillez confirmer votre email pour activer votre compte.", extra_tags="public_auth")
        else:
            messages.error(request, "Identifiants incorrects. Veuillez réessayer.", extra_tags="public_auth")

    return render(request, "login.html")


@require_http_methods(["POST"])
def logout_view(request):
    auth_logout(request)
    return redirect("welcome")


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("welcome")

    wizard = request.session.get("register_wizard") or {}
    step = request.GET.get("step") or request.POST.get("step") or wizard.get("step") or "1"
    step = str(step)
    if step not in {"1", "2", "3", "4"}:
        step = "1"

    def save_wizard(**kwargs):
        wizard.update(kwargs)
        wizard["step"] = step
        request.session["register_wizard"] = wizard
        request.session.modified = True

    if request.method == "POST":
        if step == "1":
            first_name = (request.POST.get("first_name") or "").strip()
            last_name = (request.POST.get("last_name") or "").strip()
            email = (request.POST.get("email") or "").strip().lower()
            profession = (request.POST.get("profession") or "").strip()

            if not first_name or not last_name or not email or not profession:
                messages.error(request, "Veuillez compléter tous les champs.", extra_tags="public_auth")
            elif "@" not in email or "." not in email:
                messages.error(request, "Adresse email invalide.", extra_tags="public_auth")
            elif User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
                messages.error(request, "Cet email est déjà utilisé.", extra_tags="public_auth")
            else:
                save_wizard(first_name=first_name, last_name=last_name, email=email, profession=profession)
                return redirect("/register/?step=2")

        elif step == "2":
            password1 = request.POST.get("password1") or ""
            password2 = request.POST.get("password2") or ""
            if not password1 or not password2:
                messages.error(request, "Veuillez saisir et confirmer votre mot de passe.", extra_tags="public_auth")
            elif password1 != password2:
                messages.error(request, "Les mots de passe ne correspondent pas.", extra_tags="public_auth")
            elif len(password1) < 8:
                messages.error(request, "Mot de passe trop court (8 caractères minimum).", extra_tags="public_auth")
            else:
                save_wizard(password=password1)
                return redirect("/register/?step=3")

        elif step == "3":
            accept = request.POST.get("accept_terms") == "on"
            if not accept:
                messages.error(request, "Vous devez accepter les conditions pour continuer.", extra_tags="public_auth")
            else:
                save_wizard(accept_terms=True)
                return redirect("/register/?step=4")

        elif step == "4":
            # Création finale
            email = wizard.get("email") or ""
            first_name = wizard.get("first_name") or ""
            last_name = wizard.get("last_name") or ""
            profession = wizard.get("profession") or ""
            password = wizard.get("password") or ""
            accept_terms = bool(wizard.get("accept_terms"))

            if not (email and first_name and last_name and profession and password and accept_terms):
                messages.error(request, "Informations incomplètes. Veuillez reprendre l’inscription.", extra_tags="public_auth")
                request.session.pop("register_wizard", None)
                return redirect("/register/?step=1")

            if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
                messages.error(request, "Cet email est déjà utilisé.", extra_tags="public_auth")
                return redirect("/register/?step=1")

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            # Par défaut : citoyen + email non confirmé => compte inactif
            user.is_active = False
            user.save(update_fields=["is_active"])
            if hasattr(user, "profile"):
                user.profile.role = UserRole.CITOYEN
                user.profile.email_verified = False
                user.profile.profession = profession
                user.profile.save(update_fields=["role", "email_verified", "profession"])

            token = signer.sign(str(user.pk))
            confirm_url = request.build_absolute_uri(reverse("confirm_email", args=[token]))
            try:
                send_mail(
                    subject="Confirmez votre email — Portail communal",
                    message=(
                        f"Bonjour {first_name},\n\n"
                        f"Veuillez confirmer votre email en cliquant sur ce lien (valable 10 minutes) :\n"
                        f"{confirm_url}\n\n"
                        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message."
                    ),
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                # On garde le compte créé mais on informe l'utilisateur.
                if settings.DEBUG:
                    messages.error(request, f"Erreur SMTP lors de l'envoi : {e}", extra_tags="public_auth")
                else:
                    messages.error(
                        request,
                        "Impossible d'envoyer l'email de confirmation pour le moment. "
                        "Veuillez réessayer plus tard ou contacter le support.",
                        extra_tags="public_auth",
                    )

            request.session.pop("register_wizard", None)
            return redirect("register_sent")

    # GET ou POST avec erreur : afficher étape courante
    ctx = {
        "step": int(step),
        "wizard": wizard,
    }
    return render(request, "register.html", ctx)


@login_required
def dashboard_view(request):
    if _is_admin_user(request.user):
        return redirect("hdv_dashboard")
    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Citoyen"
    qs = Demande.objects.filter(citoyen=user)
    total = qs.count()
    en_examen = qs.filter(statut=DemandeStatut.EN_EXAMEN).count()
    approuves = qs.filter(statut=DemandeStatut.APPROUVE).count()
    action_requise = qs.filter(statut=DemandeStatut.ACTION_REQUISE).count()

    def ratio_pct(part: int) -> int:
        if total <= 0:
            return 0
        return min(100, int(round(100 * part / total)))

    demandes = [
        {
            "id": d.pk,
            "ref": d.reference,
            "type": d.type_demande,
            "etat": d.get_statut_display().upper(),
            "date": timezone.localtime(d.updated_at).strftime("%d/%m/%Y"),
        }
        for d in qs[:8]
    ]

    ctx = {
        "user_display_name": display,
        "stats": {
            "dossiers_total": total,
            "en_examen": en_examen,
            "approuves": approuves,
            "action_requise": action_requise,
        },
        "bar_widths": {
            "dossiers": 100 if total else 0,
            "en_examen": ratio_pct(en_examen),
            "approuves": ratio_pct(approuves),
            "action_requise": ratio_pct(action_requise),
        },
        "demandes": demandes,
    }
    return render(request, "dashboard_clean.html", ctx)


@login_required
def documents_view(request):
    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Citoyen"
    docs = (
        Document.objects.select_related("demande", "demande__citoyen")
        .filter(demande__citoyen=user)
        .order_by("-created_at")
    )
    ctx = {
        "user_display_name": display,
        "documents": docs,
    }
    return render(request, "documents.html", ctx)


@login_required
@require_http_methods(["GET"])
@cache_control(no_store=True, no_cache=True, must_revalidate=True, private=True)
def document_download_view(request, pk: int):
    """Téléchargement autorisé uniquement pour les documents du citoyen connecté (pas d’URL /media/ directe)."""
    doc = (
        Document.objects.select_related("demande")
        .filter(pk=pk, demande__citoyen=request.user)
        .first()
    )
    if doc is None:
        raise Http404()
    if not doc.fichier or not doc.fichier.name:
        raise Http404()
    try:
        fh = doc.fichier.open("rb")
    except FileNotFoundError:
        raise Http404()
    download_name = os.path.basename(doc.fichier.name)
    resp = FileResponse(fh, as_attachment=True, filename=download_name)
    resp["Cache-Control"] = "no-store, private"
    return resp


def _require_admin_role(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if getattr(request.user, "is_superuser", False):
        return None
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role not in {UserRole.SUPER_ADMIN, UserRole.CITY_ADMIN, UserRole.ADMIN}:
        messages.error(request, "Accès refusé.", extra_tags="hdv")
        return redirect("dashboard")
    return None


def _require_hdv_role(request):
    """
    Accès Hôtel de ville : admin ville + legacy, jamais le Ministère.
    (Le Ministère ne fait pas de micro-gestion.)
    """
    if not request.user.is_authenticated:
        return redirect("login")
    if getattr(request.user, "is_superuser", False):
        return None
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role not in {UserRole.CITY_ADMIN, UserRole.ADMIN}:
        messages.error(request, "Accès refusé.", extra_tags="hdv")
        return redirect("dashboard")
    return None


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
def hdv_dashboard_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Administrateur"

    communes_qs = Commune.objects.all()
    if not getattr(request.user, "is_superuser", False):
        prof = getattr(request.user, "profile", None)
        ville = getattr(prof, "ville", None)
        communes_qs = communes_qs.filter(ville_parent=ville) if ville is not None else communes_qs.none()
    communes_total = communes_qs.count()
    communes_inactives = communes_qs.filter(active=False).count()
    communes_actives = max(0, communes_total - communes_inactives)
    communes_inactives_list = communes_qs.filter(active=False).order_by("nom")[:8]
    communes_recents = communes_qs.order_by("-updated_at")[:6]
    communes_par_province = (
        communes_qs.exclude(province="")
        .values("province")
        .annotate(c=Count("id"))
        .order_by("-c", "province")[:8]
    )

    demandes_qs = Demande.objects.all()
    demandes_total = demandes_qs.count()
    demandes_occupation = demandes_qs.filter(
        Q(type_demande__icontains="occupation") | Q(type_demande__icontains="domanial") | Q(type_demande__icontains="maison")
    ).count()

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    demandes_mois = demandes_qs.filter(created_at__gte=month_start).count()

    documents_qs = Document.objects.all()
    documents_total = documents_qs.count()
    documents_mois = documents_qs.filter(created_at__gte=month_start).count()

    fee_document = int(getattr(settings, "HDV_FEE_DOCUMENT", 0) or 0)
    fee_occupation = int(getattr(settings, "HDV_FEE_OCCUPATION", 0) or 0)
    currency = getattr(settings, "HDV_CURRENCY", "CDF")

    recettes_total = documents_total * fee_document
    recettes_mois = documents_mois * fee_document
    taxes_occupation_total = demandes_occupation * fee_occupation

    ctx = {
        "user_display_name": display,
        "kpis": {
            "communes": communes_total,
            "communes_actives": communes_actives,
            "bourgmestres": UserProfile.objects.filter(role=UserRole.CHEF_SERVICE).count(),
            "agents": UserProfile.objects.filter(role=UserRole.AGENT).count(),
            "demandes": demandes_total,
            "demandes_mois": demandes_mois,
            "communes_inactives": communes_inactives,
            "demandes_occupation": demandes_occupation,
            "documents": documents_total,
            "documents_mois": documents_mois,
        },
        "finance": {
            "currency": currency,
            "fee_document": fee_document,
            "fee_occupation": fee_occupation,
            "recettes_total": recettes_total,
            "recettes_mois": recettes_mois,
            "taxes_occupation_total": taxes_occupation_total,
        },
        "overview": {
            "communes_inactives_list": communes_inactives_list,
            "communes_recents": communes_recents,
            "communes_par_province": communes_par_province,
        },
    }
    return render(request, "hdv_dashboard.html", ctx)


@login_required
def ministere_dashboard_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    # Filtres géographiques (Province > Ville > Commune)
    province = (request.GET.get("province") or "").strip()
    ville_id = (request.GET.get("ville") or "").strip()
    commune_id = (request.GET.get("commune") or "").strip()

    villes_qs = Ville.objects.filter(active=True)
    communes_qs = Commune.objects.filter(active=True)

    if province:
        villes_qs = villes_qs.filter(Q(province__iexact=province) | Q(province__icontains=province))
        communes_qs = communes_qs.filter(Q(province__iexact=province) | Q(province__icontains=province))

    ville_obj = None
    if ville_id.isdigit():
        ville_obj = Ville.objects.filter(pk=int(ville_id)).first()
        if ville_obj is not None:
            # La relation FK `ville_parent` n'est pas disponible en base (colonne absente).
            # On filtre donc via le champ texte `Commune.ville` (nom de ville).
            communes_qs = communes_qs.filter(Q(ville__iexact=ville_obj.nom) | Q(ville__icontains=ville_obj.nom))

    commune_obj = None
    if commune_id.isdigit():
        commune_obj = Commune.objects.filter(pk=int(commune_id)).first()

    # Dossiers : on agrège par géographie via le profil du citoyen (jamais de détails nominaux).
    demandes_qs = Demande.objects.all()
    if province:
        demandes_qs = demandes_qs.filter(
            Q(citoyen__profile__ville__province__iexact=province)
            | Q(citoyen__profile__commune__province__iexact=province)
        )
    if ville_obj is not None:
        demandes_qs = demandes_qs.filter(
            Q(citoyen__profile__ville=ville_obj)
            | Q(citoyen__profile__commune__ville__iexact=ville_obj.nom)
            | Q(citoyen__profile__commune__ville__icontains=ville_obj.nom)
        )
    if commune_obj is not None:
        demandes_qs = demandes_qs.filter(citoyen__profile__commune=commune_obj)

    documents_qs = Document.objects.all()
    if province:
        documents_qs = documents_qs.filter(
            Q(demande__citoyen__profile__ville__province__iexact=province)
            | Q(demande__citoyen__profile__commune__province__iexact=province)
        )
    if ville_obj is not None:
        documents_qs = documents_qs.filter(
            Q(demande__citoyen__profile__ville=ville_obj)
            | Q(demande__citoyen__profile__commune__ville__iexact=ville_obj.nom)
            | Q(demande__citoyen__profile__commune__ville__icontains=ville_obj.nom)
        )
    if commune_obj is not None:
        documents_qs = documents_qs.filter(demande__citoyen__profile__commune=commune_obj)

    # KPIs (macro)
    demandes_total = demandes_qs.count()
    documents_total = documents_qs.count()

    # "Etat civil" (approximation via type_demande) — macro uniquement
    naissances = demandes_qs.filter(type_demande__icontains="naissance").count()
    mariages = demandes_qs.filter(type_demande__icontains="mariage").count()
    deces = demandes_qs.filter(Q(type_demande__icontains="décès") | Q(type_demande__icontains="deces")).count()

    # Denominateur population (proxy) pour taux / 1000 habitants
    population_total = (
        communes_qs.exclude(population_estimee__isnull=True).aggregate(total=models.Sum("population_estimee")).get("total")
        or 0
    )
    def per_1000(n: int, denom: int) -> float:
        if denom <= 0:
            return 0.0
        return round((n / denom) * 1000.0, 3)

    natalite_1000 = per_1000(naissances, int(population_total))
    mortalite_1000 = per_1000(deces, int(population_total))

    par_statut = list(
        demandes_qs.values("statut")
        .annotate(c=Count("id"))
        .order_by("-c", "statut")
    )

    # Décentralisation : couverture par province / ville (macro)
    villes_par_province = list(
        Ville.objects.exclude(province="")
        .values("province")
        .annotate(villes=Count("id"))
        .order_by("-villes", "province")[:12]
    )
    communes_par_province = list(
        Commune.objects.exclude(province="")
        .values("province")
        .annotate(communes=Count("id"))
        .order_by("-communes", "province")[:12]
    )

    # Densité/Population (si renseignée) — pas de données ménages pour l’instant
    communes_population = list(
        communes_qs.exclude(population_estimee__isnull=True)
        .values("id", "nom", "population_estimee", "province")
        .order_by("-population_estimee")[:12]
    )

    # Finances (placeholder cohérent avec l’existant HDV)
    fee_document = int(getattr(settings, "HDV_FEE_DOCUMENT", 0) or 0)
    currency = getattr(settings, "HDV_CURRENCY", "CDF")
    recettes_estimees = documents_total * fee_document

    # Finances réelles (si le module paiements est alimenté)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    payments_qs = CommuneTaxPayment.objects.filter(status=PaymentStatus.SUCCEEDED)
    if province:
        payments_qs = payments_qs.filter(commune__province__iexact=province)
    if ville_obj is not None:
        payments_qs = payments_qs.filter(commune__ville_parent=ville_obj)
    if commune_obj is not None:
        payments_qs = payments_qs.filter(commune=commune_obj)

    payments_total = payments_qs.aggregate(total=models.Sum("amount_cdf")).get("total") or 0
    payments_mois = payments_qs.filter(paid_at__gte=month_start).aggregate(total=models.Sum("amount_cdf")).get("total") or 0

    # Part numérique vs cash
    num_total = payments_qs.exclude(channel=PaymentChannel.CASH).aggregate(total=models.Sum("amount_cdf")).get("total") or 0
    cash_total = payments_qs.filter(channel=PaymentChannel.CASH).aggregate(total=models.Sum("amount_cdf")).get("total") or 0
    def pct(part: int, whole: int) -> int:
        if whole <= 0:
            return 0
        return int(round((part / whole) * 100))
    part_num_pct = pct(int(num_total), int(payments_total))
    part_cash_pct = pct(int(cash_total), int(payments_total))

    # IPM/IRL/Étalage (volumes)
    by_tax = list(
        payments_qs.values("tax_type")
        .annotate(total=models.Sum("amount_cdf"), n=Count("id"))
        .order_by("-total")
    )

    # Sécurité (incidents) + protection civile (zones à risque) + ASBL/Églises
    incidents_qs = SecurityIncident.objects.all()
    risks_qs = RiskZone.objects.filter(is_active=True)
    entities_qs = LegalEntity.objects.filter(is_active=True)

    if province:
        incidents_qs = incidents_qs.filter(commune__province__iexact=province)
        risks_qs = risks_qs.filter(commune__province__iexact=province)
        entities_qs = entities_qs.filter(commune__province__iexact=province)
    if ville_obj is not None:
        incidents_qs = incidents_qs.filter(commune__ville_parent=ville_obj)
        risks_qs = risks_qs.filter(commune__ville_parent=ville_obj)
        entities_qs = entities_qs.filter(commune__ville_parent=ville_obj)
    if commune_obj is not None:
        incidents_qs = incidents_qs.filter(commune=commune_obj)
        risks_qs = risks_qs.filter(commune=commune_obj)
        entities_qs = entities_qs.filter(commune=commune_obj)

    incidents_total = incidents_qs.count()
    incidents_mois = incidents_qs.filter(occurred_at__gte=month_start).count()
    incidents_by_type = list(
        incidents_qs.values("incident_type")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    risk_total = risks_qs.count()
    risk_by_type = list(
        risks_qs.values("risk_type").annotate(c=Count("id")).order_by("-c")
    )
    entities_total = entities_qs.count()
    entities_by_type = list(
        entities_qs.values("entity_type").annotate(c=Count("id")).order_by("-c")
    )

    ctx = {
        "current": "ministere_dashboard",
        "filters": {
            "province": province,
            "ville": ville_obj,
            "commune": commune_obj,
        },
        "choices": {
            "provinces": sorted(
                {p for p in Ville.objects.exclude(province="").values_list("province", flat=True) if p}
                | {p for p in Commune.objects.exclude(province="").values_list("province", flat=True) if p}
            ),
            "villes": list(villes_qs.order_by("nom")[:200]),
            "communes": list(communes_qs.order_by("nom")[:400]),
        },
        "kpis": {
            "demandes_total": demandes_total,
            "documents_total": documents_total,
            "naissances": naissances,
            "mariages": mariages,
            "deces": deces,
            "population_total": int(population_total),
            "natalite_1000": natalite_1000,
            "mortalite_1000": mortalite_1000,
            "doubles_identites": None,  # non disponible (pas d’UID encore)
        },
        "etat_civil": {
            "par_statut": par_statut,
        },
        "decentralisation": {
            "villes_par_province": villes_par_province,
            "communes_par_province": communes_par_province,
            "communes_population": communes_population,
        },
        "finances": {
            "currency": currency,
            "fee_document": fee_document,
            "recettes_estimees": recettes_estimees,
            "paiements_total": int(payments_total),
            "paiements_mois": int(payments_mois),
            "part_num_pct": part_num_pct,
            "part_cash_pct": part_cash_pct,
            "by_tax": by_tax,
        },
        "securite": {
            "incidents_total": incidents_total,
            "incidents_mois": incidents_mois,
            "incidents_by_type": incidents_by_type,
            "zones_risques_total": risk_total,
            "zones_risques_by_type": risk_by_type,
            "asbl_eglises_total": entities_total,
            "asbl_eglises_by_type": entities_by_type,
        },
    }
    return render(request, "ministere_dashboard.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def hdv_communes_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    q = (request.GET.get("q") or "").strip()
    qs = Commune.objects.all()
    prof = getattr(request.user, "profile", None)
    if not getattr(request.user, "is_superuser", False):
        ville = getattr(prof, "ville", None)
        if ville is not None:
            qs = qs.filter(ville_parent=ville)
        else:
            qs = qs.none()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(province__icontains=q) | Q(code__icontains=q))

    communes_total = qs.count()
    communes_inactives = qs.filter(active=False).count()
    communes_actives = max(0, communes_total - communes_inactives)
    provinces_renseignees = qs.exclude(province="").values("province").distinct().count()

    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
        "q": q,
        "communes": qs,
        "stats": {
            "total": communes_total,
            "actives": communes_actives,
            "inactives": communes_inactives,
            "provinces": provinces_renseignees,
        },
    }
    return render(request, "hdv_communes.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def hdv_commune_create_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    prof = getattr(request.user, "profile", None)
    if not getattr(request.user, "is_superuser", False) and (getattr(prof, "ville", None) is None):
        messages.error(request, "Votre compte Hôtel de ville n’est pas rattaché à une ville. Contactez le Ministère.", extra_tags="hdv")
        return redirect("hdv_dashboard")

    if request.method == "POST":
        ville_parent = getattr(prof, "ville", None) if not getattr(request.user, "is_superuser", False) else (getattr(prof, "ville", None) or None)
        nom = (request.POST.get("nom") or "").strip()
        province = (request.POST.get("province") or "").strip()
        code = (request.POST.get("code") or "").strip()
        ville = (request.POST.get("ville") or "").strip()
        active = request.POST.get("active") == "on"
        adresse = (request.POST.get("adresse") or "").strip()
        quartier = (request.POST.get("quartier") or "").strip()
        lat_raw = (request.POST.get("latitude") or "").strip()
        lng_raw = (request.POST.get("longitude") or "").strip()
        services_estimes_raw = (request.POST.get("services_estimes") or "").strip()
        population_raw = (request.POST.get("population_estimee") or "").strip()
        nombre_quartiers_raw = (request.POST.get("nombre_quartiers") or "").strip()
        langue_defaut = (request.POST.get("langue_defaut") or "fr").strip()
        fuseau_horaire = (request.POST.get("fuseau_horaire") or "Africa/Kinshasa").strip()

        lat = None
        lng = None
        try:
            lat = float(lat_raw) if lat_raw else None
        except ValueError:
            lat = None
        try:
            lng = float(lng_raw) if lng_raw else None
        except ValueError:
            lng = None

        def as_int(v):
            try:
                return int(v) if v != "" else None
            except ValueError:
                return None

        services_estimes = as_int(services_estimes_raw)
        population_estimee = as_int(population_raw)
        nombre_quartiers = as_int(nombre_quartiers_raw)

        if len(nom) < 2:
            messages.error(request, "Le nom de la commune est requis (au moins 2 caractères).", extra_tags="hdv")
            return redirect("hdv_commune_create")
        qs = Commune.objects.all()
        if ville_parent is not None:
            qs = qs.filter(ville_parent=ville_parent)
        if code and qs.filter(code__iexact=code).exists():
            messages.error(request, "Ce code de commune est déjà utilisé.", extra_tags="hdv")
            return redirect("hdv_commune_create")
        if qs.filter(nom__iexact=nom).exists():
            messages.error(request, "Une commune avec ce nom existe déjà.", extra_tags="hdv")
            return redirect("hdv_commune_create")
        Commune.objects.create(
            ville_parent=ville_parent,
            nom=nom,
            province=province,
            code=code,
            active=active,
            adresse=adresse,
            quartier=quartier,
            ville=ville,
            latitude=lat,
            longitude=lng,
            services_estimes=services_estimes,
            population_estimee=population_estimee,
            nombre_quartiers=nombre_quartiers,
            langue_defaut=langue_defaut or "fr",
            fuseau_horaire=fuseau_horaire or "Africa/Kinshasa",
        )
        messages.success(request, "Commune créée avec succès.", extra_tags="hdv")
        return redirect("hdv_communes")

    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_commune_create.html", ctx)


@login_required
def hdv_geo_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_geo.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def hdv_commune_edit_view(request, pk: int):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    prof = getattr(request.user, "profile", None)
    qs_obj = Commune.objects.all()
    if not getattr(request.user, "is_superuser", False):
        ville = getattr(prof, "ville", None)
        qs_obj = qs_obj.filter(ville_parent=ville) if ville is not None else qs_obj.none()
    obj = qs_obj.filter(pk=pk).first()
    if obj is None:
        messages.error(request, "Commune introuvable.", extra_tags="hdv")
        return redirect("hdv_communes")


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True, private=True)
@require_http_methods(["GET", "POST"])
def ministere_villes_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    """Ministère (super-admin) : crée une Ville et le compte principal Hôtel de ville."""
    prof = getattr(request.user, "profile", None)
    role = getattr(prof, "role", None)
    if not getattr(request.user, "is_superuser", False) and role != UserRole.SUPER_ADMIN:
        messages.error(request, "Accès refusé.", extra_tags="hdv")
        return redirect("dashboard")

    provinces = Province.objects.filter(active=True).order_by("nom")[:200]

    if request.method == "POST":
        nom = (request.POST.get("nom") or "").strip()
        province = (request.POST.get("province") or "").strip()
        code = (request.POST.get("code") or "").strip()
        active = request.POST.get("active") == "on"
        admin_email = (request.POST.get("admin_email") or "").strip().lower()
        admin_password = request.POST.get("admin_password") or ""

        if len(nom) < 2:
            messages.error(request, "Nom de ville requis.", extra_tags="hdv")
            return redirect("ministere_villes")
        if not admin_email or "@" not in admin_email:
            messages.error(request, "Email Hôtel de ville invalide.", extra_tags="hdv")
            return redirect("ministere_villes")
        if len(admin_password) < 10:
            messages.error(request, "Mot de passe Hôtel de ville trop court (10 caractères minimum).", extra_tags="hdv")
            return redirect("ministere_villes")
        if Ville.objects.filter(nom__iexact=nom).exists():
            messages.error(request, "Cette ville existe déjà.", extra_tags="hdv")
            return redirect("ministere_villes")
        if User.objects.filter(username__iexact=admin_email).exists() or User.objects.filter(email__iexact=admin_email).exists():
            messages.error(request, "Un compte avec cet email existe déjà.", extra_tags="hdv")
            return redirect("ministere_villes")

        v = Ville.objects.create(nom=nom, province=province, code=code, active=active)
        u = User.objects.create_user(username=admin_email, email=admin_email, password=admin_password, is_active=True)
        up = getattr(u, "profile", None)
        if up is None:
            up = UserProfile.objects.create(user=u)
        up.role = UserRole.CITY_ADMIN
        up.ville = v
        up.commune = None
        up.save(update_fields=["role", "ville", "commune"])

        messages.success(request, "Ville créée et compte Hôtel de ville généré.", extra_tags="hdv")
        return redirect("ministere_villes")

    villes = Ville.objects.all().order_by("nom")[:200]
    ctx = {
        "current": "ministere_villes",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip() or "Ministère",
        "villes": villes,
        "provinces": provinces,
    }
    return render(request, "ministere_villes.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def ministere_gallery_view(request):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    ville_id = (request.GET.get("ville") or "").strip()
    villes = Ville.objects.all().order_by("nom")
    selected_ville = None
    if ville_id:
        try:
            selected_ville = villes.filter(pk=int(ville_id)).first()
        except ValueError:
            selected_ville = None

    qs = GalleryPhoto.objects.all()
    if selected_ville is not None:
        qs = qs.filter(ville=selected_ville)

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        sort_order = int((request.POST.get("sort_order") or "0").strip() or 0)
        is_active = request.POST.get("is_active") == "on"
        image = request.FILES.get("image")
        post_ville_id = (request.POST.get("ville_id") or "").strip()
        desc_err = _gallery_description_error(description)

        if image is None:
            messages.error(request, "Veuillez sélectionner une image.", extra_tags="ministere")
            return redirect("ministere_gallery")
        if sort_order < 0:
            messages.error(request, "Ordre invalide.", extra_tags="ministere")
            return redirect("ministere_gallery")
        if qs.filter(sort_order=sort_order).exists():
            messages.error(request, "Cet ordre est déjà utilisé (dans ce périmètre).", extra_tags="ministere")
            return redirect("ministere_gallery")
        if desc_err:
            messages.error(request, desc_err, extra_tags="ministere")
            return redirect("ministere_gallery")

        ville_obj = None
        if post_ville_id:
            try:
                ville_obj = villes.filter(pk=int(post_ville_id)).first()
            except ValueError:
                ville_obj = None

        GalleryPhoto.objects.create(
            ville=ville_obj,
            image=image,
            title=title,
            description=description,
            sort_order=max(0, sort_order),
            is_active=is_active,
        )
        messages.success(request, "Photo ajoutée à la galerie.", extra_tags="ministere")
        return redirect("ministere_gallery")

    photos = qs.order_by("sort_order", "-created_at")[:60]
    next_sort = (qs.aggregate(m=Max("sort_order")).get("m") or 0) + 1
    ctx = {
        "current": "ministere_gallery",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Ministère",
        "photos": photos,
        "next_sort": next_sort,
        "villes": villes,
        "selected_ville": selected_ville,
    }
    return render(request, "ministere_gallery.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def ministere_gallery_edit_view(request, pk: int):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied

    obj = GalleryPhoto.objects.filter(pk=pk).first()
    if obj is None:
        messages.error(request, "Photo introuvable.", extra_tags="ministere")
        return redirect("ministere_gallery")

    villes = Ville.objects.all().order_by("nom")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        sort_order = max(0, int((request.POST.get("sort_order") or "0").strip() or 0))
        is_active = request.POST.get("is_active") == "on"
        new_image = request.FILES.get("image")
        post_ville_id = (request.POST.get("ville_id") or "").strip()
        orig_compact = " ".join((obj.description or "").split())
        new_compact = " ".join(description.split())

        if len(new_compact) > 500:
            messages.error(request, "Le texte (long) ne doit pas dépasser 500 caractères.", extra_tags="ministere")
            return redirect("ministere_gallery_edit", pk=pk)
        if GalleryPhoto.objects.exclude(pk=obj.pk).filter(sort_order=sort_order, ville=obj.ville).exists():
            messages.error(request, "Cet ordre est déjà utilisé (dans ce périmètre).", extra_tags="ministere")
            return redirect("ministere_gallery_edit", pk=pk)
        desc_err = _gallery_description_error(description) if new_compact != orig_compact else None
        if desc_err:
            messages.error(request, desc_err, extra_tags="ministere")
            return redirect("ministere_gallery_edit", pk=pk)

        ville_obj = None
        if post_ville_id:
            try:
                ville_obj = villes.filter(pk=int(post_ville_id)).first()
            except ValueError:
                ville_obj = None

        obj.ville = ville_obj
        obj.title = title
        obj.description = description
        obj.sort_order = sort_order
        obj.is_active = is_active
        if new_image is not None:
            if obj.image and getattr(obj.image, "name", ""):
                obj.image.delete(save=False)
            obj.image = new_image
        try:
            obj.full_clean()
        except ValidationError as exc:
            parts: list[str] = []
            if hasattr(exc, "error_dict") and exc.error_dict:
                for errs in exc.error_dict.values():
                    parts.extend(str(e) for e in errs)
            else:
                parts = [str(m) for m in getattr(exc, "messages", [])] or [str(exc)]
            messages.error(request, " ".join(parts), extra_tags="ministere")
            return redirect("ministere_gallery_edit", pk=pk)
        obj.save()
        messages.success(request, "Photo mise à jour.", extra_tags="ministere")
        return redirect("ministere_gallery")

    ctx = {
        "current": "ministere_gallery",
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Ministère",
        "photo": obj,
        "villes": villes,
    }
    return render(request, "ministere_gallery_edit.html", ctx)


@login_required
@require_http_methods(["POST"])
def ministere_gallery_delete_view(request, pk: int):
    denied = _require_ministere_role(request)
    if denied is not None:
        return denied
    obj = GalleryPhoto.objects.filter(pk=pk).first()
    if obj is None:
        messages.error(request, "Photo introuvable.", extra_tags="ministere")
        return redirect("ministere_gallery")
    obj.delete()
    messages.success(request, "Photo supprimée.", extra_tags="ministere")
    return redirect("ministere_gallery")


## NOTE: le référentiel géographique (provinces/communes/quartiers) est désormais dans l'app `referentiel_geo`.


@login_required
def hdv_users_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_users.html", ctx)


@login_required
def hdv_activites_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_activites.html", ctx)


@login_required
def hdv_dossiers_sensibles_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_dossiers_sensibles.html", ctx)


@login_required
def hdv_annonces_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_annonces.html", ctx)


@login_required
def hdv_audit_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
    }
    return render(request, "hdv_audit.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def hdv_gallery_view(request):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    profile = getattr(request.user, "profile", None)
    ville = getattr(profile, "ville", None)
    if ville is None:
        messages.error(request, "Aucune ville n’est associée à ce compte.", extra_tags="hdv")
        return redirect("hdv_dashboard")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        sort_order = int((request.POST.get("sort_order") or "0").strip() or 0)
        is_active = request.POST.get("is_active") == "on"
        image = request.FILES.get("image")
        desc_err = _gallery_description_error(description)

        if image is None:
            messages.error(request, "Veuillez sélectionner une image.", extra_tags="hdv")
            return redirect("hdv_gallery")
        if sort_order < 0:
            messages.error(request, "Ordre invalide.", extra_tags="hdv")
            return redirect("hdv_gallery")
        if GalleryPhoto.objects.filter(sort_order=sort_order).exists():
            messages.error(request, "Cet ordre est déjà utilisé. Choisissez un autre ordre.", extra_tags="hdv")
            return redirect("hdv_gallery")
        if desc_err:
            messages.error(request, desc_err, extra_tags="hdv")
            return redirect("hdv_gallery")
        GalleryPhoto.objects.create(
            ville=ville,
            image=image,
            title=title,
            description=description,
            sort_order=max(0, sort_order),
            is_active=is_active,
        )
        messages.success(request, "Photo ajoutée à la galerie.", extra_tags="hdv")
        return redirect("hdv_gallery")

    photos = GalleryPhoto.objects.filter(ville=ville).order_by("sort_order", "-created_at")[:40]
    next_sort = (GalleryPhoto.objects.filter(ville=ville).aggregate(m=Max("sort_order")).get("m") or 0) + 1
    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
        "scope_ville": ville,
        "photos": photos,
        "next_sort": next_sort,
    }
    return render(request, "hdv_gallery.html", ctx)


@login_required
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@require_http_methods(["GET", "POST"])
def hdv_gallery_edit_view(request, pk: int):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    profile = getattr(request.user, "profile", None)
    ville = getattr(profile, "ville", None)
    if ville is None:
        messages.error(request, "Aucune ville n’est associée à ce compte.", extra_tags="hdv")
        return redirect("hdv_dashboard")

    obj = GalleryPhoto.objects.filter(pk=pk, ville=ville).first()
    if obj is None:
        messages.error(request, "Photo introuvable.", extra_tags="hdv")
        return redirect("hdv_gallery")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        sort_order = max(0, int((request.POST.get("sort_order") or "0").strip() or 0))
        is_active = request.POST.get("is_active") == "on"
        new_image = request.FILES.get("image")
        orig_compact = " ".join((obj.description or "").split())
        new_compact = " ".join(description.split())

        if len(new_compact) > 500:
            messages.error(request, "Le texte (long) ne doit pas dépasser 500 caractères.", extra_tags="hdv")
            return redirect("hdv_gallery_edit", pk=pk)
        if GalleryPhoto.objects.exclude(pk=obj.pk).filter(sort_order=sort_order).exists():
            messages.error(request, "Cet ordre est déjà utilisé. Choisissez un autre ordre.", extra_tags="hdv")
            return redirect("hdv_gallery_edit", pk=pk)
        # Si le texte n’a pas changé, on ne ré-applique pas la règle “hero” (sinon les anciennes données
        # peuvent bloquer toute sauvegarde, y compris le remplacement d’image).
        desc_err = _gallery_description_error(description) if new_compact != orig_compact else None
        if desc_err:
            messages.error(request, desc_err, extra_tags="hdv")
            return redirect("hdv_gallery_edit", pk=pk)
        obj.title = title
        obj.description = description
        obj.sort_order = sort_order
        obj.is_active = is_active
        if new_image is not None:
            if obj.image and getattr(obj.image, "name", ""):
                obj.image.delete(save=False)
            obj.image = new_image
        try:
            obj.full_clean()
        except ValidationError as exc:
            parts: list[str] = []
            if hasattr(exc, "error_dict") and exc.error_dict:
                for errs in exc.error_dict.values():
                    parts.extend(str(e) for e in errs)
            else:
                parts = [str(m) for m in getattr(exc, "messages", [])] or [str(exc)]
            messages.error(request, " ".join(parts), extra_tags="hdv")
            return redirect("hdv_gallery_edit", pk=pk)
        obj.save()
        messages.success(request, "Photo mise à jour.", extra_tags="hdv")
        return redirect("hdv_gallery")

    ctx = {
        "user_display_name": (request.user.first_name or request.user.get_full_name() or request.user.username).strip()
        or "Administrateur",
        "photo": obj,
    }
    return render(request, "hdv_gallery_edit.html", ctx)


@login_required
@require_http_methods(["POST"])
def hdv_gallery_delete_view(request, pk: int):
    denied = _require_hdv_role(request)
    if denied is not None:
        return denied

    profile = getattr(request.user, "profile", None)
    ville = getattr(profile, "ville", None)
    if ville is None:
        messages.error(request, "Aucune ville n’est associée à ce compte.", extra_tags="hdv")
        return redirect("hdv_dashboard")

    obj = GalleryPhoto.objects.filter(pk=pk, ville=ville).first()
    if obj is None:
        messages.error(request, "Photo introuvable.", extra_tags="hdv")
        return redirect("hdv_gallery")
    obj.delete()
    messages.success(request, "Photo supprimée.", extra_tags="hdv")
    return redirect("hdv_gallery")


DOCUMENT_CREATE_OPTIONS = (
    {
        "type": "Attestation de résidence",
        "icon": "home_work",
        "hint": "Justificatif de domicile auprès de la mairie.",
    },
    {
        "type": "Attestation de bonne vie et mœurs",
        "icon": "gavel",
        "hint": "Souvent demandée pour un emploi ou une inscription.",
    },
    {
        "type": "Certificat de nationalité (copie légalisée / attestation)",
        "icon": "badge",
        "hint": "Démarche d’état civil liée à la nationalité.",
    },
    {
        "type": "Certificat de vie",
        "icon": "favorite",
        "hint": "Attestation de présence en vie pour un organisme.",
    },
    {
        "type": "Certificat de célibat / mariage / divorce (selon dossier)",
        "icon": "diversity_3",
        "hint": "Selon votre situation matrimoniale et les pièces fournies.",
    },
    {
        "type": "Autorisation d’occupation / domaniale (dossier communal)",
        "icon": "map",
        "hint": "Dossier lié au foncier ou à l’occupation du domaine.",
    },
    {
        "type": "Autre document communal",
        "icon": "description",
        "hint": "Demande générique ; précisez au guichet si besoin.",
    },
)

DOCUMENT_TYPES_COMMUNE = tuple(o["type"] for o in DOCUMENT_CREATE_OPTIONS)


@login_required
@require_http_methods(["GET", "POST"])
def demandes_view(request):
    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Citoyen"

    qs = Demande.objects.filter(citoyen=user).prefetch_related("documents")

    q = (request.GET.get("q") or "").strip()
    statut = (request.GET.get("statut") or "").strip()
    categorie = (request.GET.get("categorie") or "").strip()

    if q:
        qs = qs.filter(Q(pk__icontains=q) | Q(type_demande__icontains=q))
    if statut:
        qs = qs.filter(statut=statut)
    if categorie:
        qs = qs.filter(type_demande=categorie)

    total = Demande.objects.filter(citoyen=user).count()
    brouillon = Demande.objects.filter(citoyen=user, statut=DemandeStatut.BROUILLON).count()
    action_requise = Demande.objects.filter(citoyen=user, statut=DemandeStatut.ACTION_REQUISE).count()
    en_attente = brouillon + action_requise
    en_traitement = Demande.objects.filter(citoyen=user, statut=DemandeStatut.EN_EXAMEN).count()
    approuvees = Demande.objects.filter(citoyen=user, statut=DemandeStatut.APPROUVE).count()

    demandes_rows = []
    for d in qs:
        first_doc = d.documents.all()[:1]
        doc = first_doc[0] if first_doc else None
        demandes_rows.append(
            {
                "id": d.pk,
                "reference": d.reference,
                "type_demande": d.type_demande,
                "statut": d.statut,
                "statut_label": d.get_statut_display(),
                "created_at": d.created_at,
                "updated_at": d.updated_at,
                "first_document": doc,
            }
        )

    ctx = {
        "user_display_name": display,
        "filters": {
            "q": q,
            "statut": statut,
            "categorie": categorie,
        },
        "stats": {
            "total": total,
            "en_attente": en_attente,
            "en_traitement": en_traitement,
            "approuvees": approuvees,
        },
        "demandes": demandes_rows,
        "result_count": len(demandes_rows),
        "statut_choices": DemandeStatut.choices,
        "document_types": DOCUMENT_TYPES_COMMUNE,
        "sync_at": timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M"),
    }
    return render(request, "demandes.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def demande_create_view(request):
    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Citoyen"

    form_data = _demande_form_from_post(request.POST) if request.method == "POST" else _demande_form_defaults(user)

    if request.method == "POST":
        type_demande = (request.POST.get("type_demande") or "").strip()
        accept = request.POST.get("accept_terms") == "on"
        type_ok = type_demande in DOCUMENT_TYPES_COMMUNE
        field_errors = _validate_demande_form(form_data) if type_ok else []
        if not type_ok:
            messages.error(request, "Type de document invalide. Veuillez recommencer le parcours.")
        else:
            for msg in field_errors:
                messages.error(request, msg)
            if not accept:
                messages.error(request, "Vous devez accepter les conditions pour déposer une demande.")
            elif not field_errors:
                d = Demande.objects.create(
                    citoyen=user,
                    type_demande=type_demande,
                    statut=DemandeStatut.BROUILLON,
                    declarant_nom=form_data["declarant_nom"],
                    declarant_telephone=form_data["declarant_telephone"],
                    declarant_email=form_data["declarant_email"],
                    declarant_adresse=form_data["declarant_adresse"],
                    motif_precisions=form_data["motif_precisions"],
                )
                messages.success(
                    request,
                    "Votre demande a été créée en brouillon. Vous pouvez maintenant consulter le dossier et préparer les pièces demandées par la mairie.",
                )
                return redirect("demande_detail", pk=d.pk)

    if request.method == "POST":
        posted = (request.POST.get("type_demande") or "").strip()
        preselect = posted if posted in DOCUMENT_TYPES_COMMUNE else ""
    else:
        preselect = (request.GET.get("type") or "").strip()
        if preselect not in DOCUMENT_TYPES_COMMUNE:
            preselect = ""

    ctx = {
        "user_display_name": display,
        "document_options": DOCUMENT_CREATE_OPTIONS,
        "preselect_type": preselect,
        "form_data": form_data,
        "wizard_resume": request.method == "POST",
    }
    return render(request, "demande_nouvelle.html", ctx)


@login_required
@require_http_methods(["GET"])
def demande_detail_view(request, pk: int):
    user = request.user
    display = (user.first_name or user.get_full_name() or user.username).strip() or "Citoyen"
    demande = (
        Demande.objects.prefetch_related("documents")
        .filter(pk=pk, citoyen=user)
        .first()
    )
    if demande is None:
        messages.error(request, "Dossier introuvable.")
        return redirect("demandes")

    ctx = {
        "user_display_name": display,
        "demande": demande,
        "documents": demande.documents.all(),
    }
    return render(request, "demande_detail.html", ctx)


@require_http_methods(["GET"])
def register_sent_view(request):
    return render(request, "register_sent.html")


@require_http_methods(["GET"])
def confirm_email_view(request, token: str):
    try:
        unsigned = signer.unsign(token, max_age=60 * 10)  # 10 minutes
        user_id = int(unsigned)
        user = User.objects.get(pk=user_id)
    except (BadSignature, SignatureExpired, ValueError, User.DoesNotExist):
        messages.error(request, "Lien invalide ou expiré. Veuillez recommencer l’inscription.", extra_tags="public_auth")
        return redirect("register")

    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    if hasattr(user, "profile") and not user.profile.email_verified:
        user.profile.email_verified = True
        user.profile.save(update_fields=["email_verified"])

    messages.success(request, "Email confirmé. Vous pouvez vous connecter.", extra_tags="public_auth")
    return redirect("login")


@require_http_methods(["GET", "POST"])
def password_reset_request_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        # Réponse neutre pour ne pas révéler si l'email existe
        neutral_msg = "Si un compte correspond à cet email, un code de réinitialisation vient d’être envoyé."

        user = None
        if email and "@" in email:
            user = User.objects.filter(email=email).first()

        if user:
            code = f"{secrets.randbelow(1_000_000):06d}"
            expires_at = timezone.now() + timezone.timedelta(minutes=10)
            code_hash = salted_hmac(
                key_salt="sisepcommune.password_reset",
                value=f"{user.pk}:{code}",
                secret=settings.SECRET_KEY,
            ).hexdigest()
            PasswordResetCode.objects.create(user=user, code_hash=code_hash, expires_at=expires_at)
            try:
                send_mail(
                    subject="Code de réinitialisation — Portail communal",
                    message=(
                        "Vous avez demandé la réinitialisation de votre mot de passe.\n\n"
                        f"Votre code (valable 10 minutes) : {code}\n\n"
                        "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message."
                    ),
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                if settings.DEBUG:
                    messages.error(request, f"Erreur SMTP lors de l'envoi : {e}", extra_tags="public_auth")
                else:
                    messages.error(request, "Impossible d'envoyer l'email pour le moment. Veuillez réessayer.", extra_tags="public_auth")
                return render(request, "password_reset.html")

        request.session["pw_reset_email"] = email
        request.session["pw_reset_sent_at"] = int(timezone.now().timestamp())
        messages.success(request, neutral_msg, extra_tags="public_auth")
        return redirect("password_reset_verify")

    return render(request, "password_reset.html")


@require_http_methods(["GET", "POST"])
def password_reset_verify_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    email = (request.session.get("pw_reset_email") or "").strip().lower()
    sent_at = int(request.session.get("pw_reset_sent_at") or 0)
    expires_at_ts = sent_at + 10 * 60 if sent_at else 0

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        password1 = request.POST.get("password1") or ""
        password2 = request.POST.get("password2") or ""

        if not email:
            messages.error(request, "Session expirée. Veuillez recommencer la réinitialisation.", extra_tags="public_auth")
            return redirect("password_reset")

        if not re.fullmatch(r"\d{6}", code or ""):
            messages.error(request, "Code invalide. Entrez les 6 chiffres reçus par email.", extra_tags="public_auth")
        elif not password1 or not password2:
            messages.error(request, "Veuillez saisir et confirmer votre nouveau mot de passe.", extra_tags="public_auth")
        elif password1 != password2:
            messages.error(request, "Les mots de passe ne correspondent pas.", extra_tags="public_auth")
        elif len(password1) < 8:
            messages.error(request, "Mot de passe trop court (8 caractères minimum).", extra_tags="public_auth")
        else:
            user = User.objects.filter(email=email).first()
            if not user:
                messages.error(request, "Code invalide ou expiré. Veuillez recommencer.", extra_tags="public_auth")
                return redirect("password_reset")

            code_hash = salted_hmac(
                key_salt="sisepcommune.password_reset",
                value=f"{user.pk}:{code}",
                secret=settings.SECRET_KEY,
            ).hexdigest()
            now = timezone.now()
            prc = (
                PasswordResetCode.objects.filter(user=user, code_hash=code_hash, used_at__isnull=True, expires_at__gt=now)
                .order_by("-created_at")
                .first()
            )
            if not prc:
                messages.error(request, "Code invalide ou expiré. Veuillez recommencer.", extra_tags="public_auth")
            else:
                user.set_password(password1)
                user.save(update_fields=["password"])
                prc.used_at = now
                prc.save(update_fields=["used_at"])
                request.session.pop("pw_reset_email", None)
                request.session.pop("pw_reset_sent_at", None)
                messages.success(request, "Mot de passe mis à jour. Vous pouvez vous connecter.", extra_tags="public_auth")
                return redirect("login")

    ctx = {
        "email": email,
        "expires_at_ts": expires_at_ts,
    }
    return render(request, "password_reset_verify.html", ctx)
