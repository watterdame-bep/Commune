from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.urls import reverse
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils.crypto import salted_hmac
from django.conf import settings
import secrets
import re

from accounts.models import Demande, DemandeStatut, Document, PasswordResetCode, UserRole

signer = TimestampSigner(salt="sisepcommune.email")


def welcome(request):
    """Page d'accueil publique — point d'entrée du portail (landing)."""
    return render(request, 'welcome.html')


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('welcome')

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next")
            return redirect(next_url or "dashboard")
        # Message plus clair si le compte existe mais n'est pas activé
        if username and User.objects.filter(username=username, is_active=False).exists():
            messages.error(request, "Veuillez confirmer votre email pour activer votre compte.")
        else:
            messages.error(request, "Identifiants incorrects. Veuillez réessayer.")

    return render(request, "login.html")


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
                messages.error(request, "Veuillez compléter tous les champs.")
            elif "@" not in email or "." not in email:
                messages.error(request, "Adresse email invalide.")
            elif User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
                messages.error(request, "Cet email est déjà utilisé.")
            else:
                save_wizard(first_name=first_name, last_name=last_name, email=email, profession=profession)
                return redirect("/register/?step=2")

        elif step == "2":
            password1 = request.POST.get("password1") or ""
            password2 = request.POST.get("password2") or ""
            if not password1 or not password2:
                messages.error(request, "Veuillez saisir et confirmer votre mot de passe.")
            elif password1 != password2:
                messages.error(request, "Les mots de passe ne correspondent pas.")
            elif len(password1) < 8:
                messages.error(request, "Mot de passe trop court (8 caractères minimum).")
            else:
                save_wizard(password=password1)
                return redirect("/register/?step=3")

        elif step == "3":
            accept = request.POST.get("accept_terms") == "on"
            if not accept:
                messages.error(request, "Vous devez accepter les conditions pour continuer.")
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
                messages.error(request, "Informations incomplètes. Veuillez reprendre l’inscription.")
                request.session.pop("register_wizard", None)
                return redirect("/register/?step=1")

            if User.objects.filter(username=email).exists() or User.objects.filter(email=email).exists():
                messages.error(request, "Cet email est déjà utilisé.")
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
                    messages.error(request, f"Erreur SMTP lors de l'envoi : {e}")
                else:
                    messages.error(
                        request,
                        "Impossible d'envoyer l'email de confirmation pour le moment. "
                        "Veuillez réessayer plus tard ou contacter le support.",
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
    return render(request, "dashboard.html", ctx)


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
        messages.error(request, "Lien invalide ou expiré. Veuillez recommencer l’inscription.")
        return redirect("register")

    if not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])
    if hasattr(user, "profile") and not user.profile.email_verified:
        user.profile.email_verified = True
        user.profile.save(update_fields=["email_verified"])

    messages.success(request, "Email confirmé. Vous pouvez vous connecter.")
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
                    messages.error(request, f"Erreur SMTP lors de l'envoi : {e}")
                else:
                    messages.error(request, "Impossible d'envoyer l'email pour le moment. Veuillez réessayer.")
                return render(request, "password_reset.html")

        request.session["pw_reset_email"] = email
        request.session["pw_reset_sent_at"] = int(timezone.now().timestamp())
        messages.success(request, neutral_msg)
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
            messages.error(request, "Session expirée. Veuillez recommencer la réinitialisation.")
            return redirect("password_reset")

        if not re.fullmatch(r"\d{6}", code or ""):
            messages.error(request, "Code invalide. Entrez les 6 chiffres reçus par email.")
        elif not password1 or not password2:
            messages.error(request, "Veuillez saisir et confirmer votre nouveau mot de passe.")
        elif password1 != password2:
            messages.error(request, "Les mots de passe ne correspondent pas.")
        elif len(password1) < 8:
            messages.error(request, "Mot de passe trop court (8 caractères minimum).")
        else:
            user = User.objects.filter(email=email).first()
            if not user:
                messages.error(request, "Code invalide ou expiré. Veuillez recommencer.")
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
                messages.error(request, "Code invalide ou expiré. Veuillez recommencer.")
            else:
                user.set_password(password1)
                user.save(update_fields=["password"])
                prc.used_at = now
                prc.save(update_fields=["used_at"])
                request.session.pop("pw_reset_email", None)
                request.session.pop("pw_reset_sent_at", None)
                messages.success(request, "Mot de passe mis à jour. Vous pouvez vous connecter.")
                return redirect("login")

    ctx = {
        "email": email,
        "expires_at_ts": expires_at_ts,
    }
    return render(request, "password_reset_verify.html", ctx)
