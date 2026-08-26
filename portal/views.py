import base64
import io
import json
import secrets
import urllib.parse
import urllib.request
from datetime import timedelta
from decimal import Decimal

import pyotp
import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseGone
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .contract_templates.loan_agreement_nl_v1 import agreement_snapshot
from .forms import ApplicationForm, ContractForm, MFAForm, OTPForm, SignatureForm, StaffLoginForm
from .models import AdminMFADevice, Contract, LoanApplication, SignatureEvidence, SigningSession, StaffProfile
from .security import (
    audit,
    decrypt_value,
    encrypt_value,
    request_fingerprints,
    owner_required,
    reset_throttle,
    sha256_text,
    staff_mfa_required,
    throttle,
    verify_otp,
)
from .services import (
    build_schedule,
    create_signing_session,
    issue_signing_otp,
    save_draft_pdf,
    save_final_pdf,
    send_signing_email,
)


def _turnstile_valid(request) -> bool:
    if settings.DEMO_MODE:
        return True
    token = request.POST.get("cf-turnstile-response", "")
    if not token:
        return False
    data = urllib.parse.urlencode(
        {"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": request.META.get("REMOTE_ADDR", "")}
    ).encode()
    try:
        with urllib.request.urlopen("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=data, timeout=5) as response:
            result = json.loads(response.read().decode())
        return bool(result.get("success"))
    except Exception:
        return False


@require_GET
def home(request):
    return render(request, "portal/home.html")


def apply(request):
    if request.method == "POST":
        identity = request.POST.get("email", "anonymous")[:254]
        if not throttle(request, "public_application", identity, limit=5, window_seconds=3600, lock_seconds=3600):
            return HttpResponse("Too many attempts. Try again later.", status=429)
        form = ApplicationForm(request.POST)
        form_valid = form.is_valid()
        turnstile_valid = _turnstile_valid(request) if form_valid else True
        if form_valid and turnstile_valid:
            ip_hash, ua_hash = request_fingerprints(request)
            application = form.save(commit=False)
            application.email = application.email.casefold()
            application.terms_version = settings.TERMS_VERSION
            application.privacy_version = settings.PRIVACY_VERSION
            application.terms_accepted_at = timezone.now()
            application.privacy_accepted_at = timezone.now()
            application.submitted_ip_hash = ip_hash
            application.user_agent_hash = ua_hash
            application.is_demo = settings.DEMO_MODE
            application.retention_until = timezone.localdate() + timedelta(days=365)
            application.save()
            reset_throttle(request, "public_application", identity)
            audit(action="application.submitted", object_type="application", object_id=application.id, actor_type="applicant", actor_reference=application.email, metadata={"demo": settings.DEMO_MODE})
            request.session["submitted_reference"] = application.reference
            send_mail(
                subject=f"Application received - {application.reference}",
                message=f"We received your application. Your reference is {application.reference}. Do not send identity documents by normal email.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[application.email],
                fail_silently=settings.DEMO_MODE,
            )
            return redirect("application_success")
        if form_valid and not turnstile_valid:
            form.add_error(None, "Security verification failed. Please try again.")
    else:
        form = ApplicationForm()
    return render(request, "portal/apply.html", {"form": form, "turnstile_site_key": settings.TURNSTILE_SITE_KEY})


@require_GET
def application_success(request):
    reference = request.session.pop("submitted_reference", None)
    if not reference:
        return redirect("home")
    return render(request, "portal/application_success.html", {"reference": reference})


@require_GET
def privacy(request):
    return render(request, "portal/privacy.html", {"privacy_version": settings.PRIVACY_VERSION})


@require_GET
def terms(request):
    return render(request, "portal/terms.html", {"terms_version": settings.TERMS_VERSION})


def _preauth_user(request):
    user_id = request.session.get("preauth_user_id")
    started = request.session.get("preauth_started_at")
    if not user_id or not started:
        return None
    try:
        started_at = timezone.datetime.fromisoformat(started)
        if timezone.is_naive(started_at):
            started_at = timezone.make_aware(started_at)
    except (TypeError, ValueError):
        return None
    if timezone.now() - started_at > timedelta(minutes=10):
        return None
    return User.objects.filter(pk=user_id, is_active=True, is_staff=True).first()


def staff_login(request):
    if request.user.is_authenticated:
        logout(request)
    form = StaffLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        if not throttle(request, "admin_login", username, limit=5, window_seconds=900, lock_seconds=1800):
            form.add_error(None, "Login temporarily locked. Try again later.")
        else:
            user = authenticate(request, username=username, password=form.cleaned_data["password"])
            if user and user.is_staff and user.is_active:
                request.session.flush()
                request.session["preauth_user_id"] = user.pk
                request.session["preauth_started_at"] = timezone.now().isoformat()
                reset_throttle(request, "admin_login", username)
                device = AdminMFADevice.objects.filter(user=user, confirmed_at__isnull=False).first()
                return redirect("staff_mfa_verify" if device else "staff_mfa_setup")
            form.add_error(None, "Invalid credentials.")
    return render(request, "portal/staff/login.html", {"form": form})


def _finish_staff_login(request, user):
    request.session.pop("preauth_user_id", None)
    request.session.pop("preauth_started_at", None)
    login(request, user)
    request.session.cycle_key()
    request.session["mfa_verified_user_id"] = user.pk
    request.session["mfa_verified_at"] = timezone.now().isoformat()
    audit(action="admin.mfa_login", object_type="user", object_id=user.pk, actor_type="admin", actor_reference=user.username)


def staff_mfa_setup(request):
    user = _preauth_user(request)
    if not user:
        return redirect("staff_login")
    if AdminMFADevice.objects.filter(user=user, confirmed_at__isnull=False).exists():
        return redirect("staff_mfa_verify")
    secret = request.session.get("mfa_setup_secret") or pyotp.random_base32()
    request.session["mfa_setup_secret"] = secret
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email or user.username, issuer_name=settings.PUBLIC_BRAND_NAME)
    qr = qrcode.make(uri)
    qr_buffer = io.BytesIO()
    qr.save(qr_buffer, format="PNG")
    qr_data = base64.b64encode(qr_buffer.getvalue()).decode()
    form = MFAForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if pyotp.TOTP(secret).verify(form.cleaned_data["code"], valid_window=1):
            recovery_codes = [secrets.token_hex(5).upper() for _ in range(8)]
            AdminMFADevice.objects.update_or_create(
                user=user,
                defaults={
                    "encrypted_secret": encrypt_value(secret),
                    "confirmed_at": timezone.now(),
                    "recovery_code_hashes": [make_password(code) for code in recovery_codes],
                },
            )
            request.session.pop("mfa_setup_secret", None)
            request.session["new_recovery_codes"] = recovery_codes
            _finish_staff_login(request, user)
            return redirect("staff_recovery_codes")
        form.add_error("code", "The authenticator code is invalid.")
    return render(request, "portal/staff/mfa_setup.html", {"form": form, "secret": secret, "qr_data": qr_data})


def staff_mfa_verify(request):
    user = _preauth_user(request)
    if not user:
        return redirect("staff_login")
    device = get_object_or_404(AdminMFADevice, user=user, confirmed_at__isnull=False)
    form = MFAForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"].replace("-", "").replace(" ", "").upper()
        valid = pyotp.TOTP(decrypt_value(device.encrypted_secret)).verify(code, valid_window=1)
        if not valid:
            for index, encoded in enumerate(device.recovery_code_hashes):
                if check_password(code, encoded):
                    device.recovery_code_hashes.pop(index)
                    device.save(update_fields=["recovery_code_hashes"])
                    valid = True
                    break
        if valid:
            _finish_staff_login(request, user)
            return redirect("staff_dashboard")
        form.add_error("code", "The authenticator or recovery code is invalid.")
    return render(request, "portal/staff/mfa_verify.html", {"form": form})


@staff_mfa_required
def staff_recovery_codes(request):
    codes = request.session.pop("new_recovery_codes", None)
    if not codes:
        return redirect("staff_dashboard")
    return render(request, "portal/staff/recovery_codes.html", {"codes": codes})


@require_POST
@staff_mfa_required
def staff_logout(request):
    logout(request)
    request.session.flush()
    return redirect("home")


@staff_mfa_required
def staff_dashboard(request):
    recent = LoanApplication.objects.all()[:8]
    counts = {key: LoanApplication.objects.filter(status=key).count() for key, _ in LoanApplication.Status.choices}
    return render(request, "portal/staff/dashboard.html", {"recent": recent, "counts": counts})


@staff_mfa_required
def staff_applications(request):
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    applications = LoanApplication.objects.all()
    if status in LoanApplication.Status.values:
        applications = applications.filter(status=status)
    if query:
        from django.db.models import Q

        applications = applications.filter(Q(reference__icontains=query) | Q(full_name__icontains=query) | Q(email__icontains=query))
    return render(request, "portal/staff/applications.html", {"applications": applications[:100], "status_filter": status, "query": query, "statuses": LoanApplication.Status.choices})


@staff_mfa_required
def staff_application_detail(request, application_id):
    application = get_object_or_404(LoanApplication, pk=application_id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        allowed = {LoanApplication.Status.REVIEW, LoanApplication.Status.MORE_INFO, LoanApplication.Status.APPROVED, LoanApplication.Status.DECLINED, LoanApplication.Status.CLOSED}
        if new_status in allowed:
            old = application.status
            application.status = new_status
            application.save(update_fields=["status", "updated_at"])
            audit(action="application.status_changed", object_type="application", object_id=application.id, actor_type="admin", actor_reference=request.user.username, metadata={"from": old, "to": new_status})
            messages.success(request, "Application status updated.")
            return redirect("staff_application_detail", application_id=application.id)
    return render(request, "portal/staff/application_detail.html", {"application": application, "contracts": application.contracts.all()})


@owner_required
def staff_contract_create(request, application_id):
    application = get_object_or_404(LoanApplication, pk=application_id)
    if application.status != LoanApplication.Status.APPROVED:
        messages.error(request, "Approve the application before creating a contract.")
        return redirect("staff_application_detail", application_id=application.id)
    initial = {"principal": application.requested_amount, "interest_amount": Decimal("0.00"), "total_repayment": application.requested_amount, "apr_percent": Decimal("0.00"), "term_months": 2}
    form = ContractForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            contract = form.save(commit=False)
            contract.application = application
            contract.template_version = settings.CONTRACT_TEMPLATE_VERSION
            contract.agreement_text_snapshot = agreement_snapshot()
            contract.installment_schedule = build_schedule(contract.total_repayment, contract.term_months, contract.first_payment_date)
            contract.lender_accepted_at = timezone.now()
            contract.created_by = request.user
            contract.save()
            save_draft_pdf(contract)
            audit(action="contract.created", object_type="contract", object_id=contract.id, actor_type="admin", actor_reference=request.user.username, metadata={"application": application.reference, "template": contract.template_version})
        messages.success(request, "Draft contract created. Review the PDF before sending it.")
        return redirect("staff_application_detail", application_id=application.id)
    return render(request, "portal/staff/contract_form.html", {"form": form, "application": application})


@staff_mfa_required
def staff_contract_pdf(request, contract_id, final=False):
    contract = get_object_or_404(Contract.objects.select_related("application"), pk=contract_id)
    field = contract.final_pdf if final else contract.draft_pdf
    if not field:
        raise Http404
    audit(action="contract.downloaded", object_type="contract", object_id=contract.id, actor_type="admin", actor_reference=request.user.username, metadata={"final": final})
    return FileResponse(field.open("rb"), content_type="application/pdf", filename=f"agreement-{contract.application.reference}{'-signed' if final else '-draft'}.pdf")


@require_POST
@owner_required
def staff_contract_send(request, contract_id):
    contract = get_object_or_404(Contract, pk=contract_id, status=Contract.Status.DRAFT)
    session, raw_token = create_signing_session(contract)
    send_signing_email(contract, raw_token)
    contract.status = Contract.Status.SENT
    contract.sent_at = timezone.now()
    contract.save(update_fields=["status", "sent_at", "updated_at"])
    contract.application.status = LoanApplication.Status.CONTRACT_SENT
    contract.application.save(update_fields=["status", "updated_at"])
    audit(action="contract.sent", object_type="contract", object_id=contract.id, actor_type="admin", actor_reference=request.user.username, metadata={"session": str(session.id)})
    messages.success(request, "The secure signing link was sent.")
    return redirect("staff_application_detail", application_id=contract.application_id)


def _signing_session(token: str) -> SigningSession:
    session = SigningSession.objects.select_related("contract__application").filter(token_hash=sha256_text(token)).first()
    if not session:
        raise Http404
    return session


def sign_contract(request, token):
    session = _signing_session(token)
    if session.expires_at <= timezone.now():
        return HttpResponseGone("This signing link has expired.")
    if session.consumed_at:
        return render(request, "portal/sign_complete.html", {"session": session, "token": token})
    otp_verified = bool(session.otp_verified_at and timezone.now() - session.otp_verified_at < timedelta(minutes=15))
    if request.method == "POST" and request.POST.get("action") == "send_otp":
        if not throttle(request, "signing_otp_send", session.token_hash, limit=3, window_seconds=600, lock_seconds=600):
            messages.error(request, "Too many code requests. Try again later.")
        else:
            issue_signing_otp(session)
            messages.success(request, "A six-digit verification code was sent.")
        return redirect("sign_contract", token=token)
    if request.method == "POST" and request.POST.get("action") == "verify_otp":
        otp_form = OTPForm(request.POST)
        if otp_form.is_valid() and session.otp_expires_at and session.otp_expires_at > timezone.now() and session.otp_attempts < 5 and verify_otp(otp_form.cleaned_data["code"], session.otp_hash):
            session.otp_verified_at = timezone.now()
            session.save(update_fields=["otp_verified_at"])
            return redirect("sign_contract", token=token)
        session.otp_attempts += 1
        session.save(update_fields=["otp_attempts"])
        messages.error(request, "The verification code is invalid or expired.")
        return redirect("sign_contract", token=token)
    if request.method == "POST" and request.POST.get("action") == "sign":
        if not otp_verified:
            return HttpResponse("Verification required.", status=403)
        form = SignatureForm(request.POST, expected_name=session.contract.application.full_name)
        if form.is_valid():
            contract = session.contract
            ip_hash, ua_hash = request_fingerprints(request)
            with transaction.atomic():
                evidence = SignatureEvidence(
                    contract=contract,
                    signer_typed_name=form.cleaned_data["typed_name"],
                    signer_email=contract.application.email,
                    agreed_at=timezone.now(),
                    document_hash_at_signing=contract.draft_document_hash,
                    ip_hash=ip_hash,
                    user_agent_hash=ua_hash,
                    consent_text_version=settings.TERMS_VERSION,
                )
                evidence.signature_image.save(f"signature-{contract.id}.png", ContentFile(form.signature_bytes), save=False)
                evidence.save()
                contract.status = Contract.Status.SIGNED
                contract.signed_at = timezone.now()
                contract.save(update_fields=["status", "signed_at", "updated_at"])
                contract.application.status = LoanApplication.Status.SIGNED
                contract.application.save(update_fields=["status", "updated_at"])
                session.consumed_at = timezone.now()
                session.save(update_fields=["consumed_at"])
                save_final_pdf(contract, form.signature_bytes)
                audit(action="contract.signed", object_type="contract", object_id=contract.id, actor_type="applicant", actor_reference=contract.application.email, metadata={"draft_hash": contract.draft_document_hash, "final_hash": contract.final_document_hash})
            send_mail(
                subject=f"Signed agreement ready - {contract.application.reference}",
                message=f"Your agreement has been signed. Return to the secure link to download your final copy: {settings.SITE_BASE_URL}{request.path}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[contract.application.email],
                fail_silently=settings.DEMO_MODE,
            )
            return redirect("sign_contract", token=token)
    else:
        form = SignatureForm(expected_name=session.contract.application.full_name)
    return render(request, "portal/sign_contract.html", {"session": session, "token": token, "otp_verified": otp_verified, "otp_form": OTPForm(), "form": form})


def signer_contract_pdf(request, token, final=False):
    session = _signing_session(token)
    if session.expires_at <= timezone.now():
        return HttpResponseGone("This signing link has expired.")
    contract = session.contract
    otp_verified = bool(session.otp_verified_at and timezone.now() - session.otp_verified_at < timedelta(minutes=15))
    if not session.consumed_at and not otp_verified:
        return HttpResponse("Email verification is required before viewing the agreement.", status=403)
    field = contract.final_pdf if final and session.consumed_at else contract.draft_pdf
    if not field:
        raise Http404
    return FileResponse(field.open("rb"), content_type="application/pdf", filename=f"agreement-{contract.application.reference}{'-signed' if final and session.consumed_at else '-draft'}.pdf")
