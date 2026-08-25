import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from functools import wraps

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone

from .models import AuditEvent, ThrottleBucket


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_hash(value: str) -> str:
    return hmac.new(settings.IP_HASH_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def client_ip(request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
        if cf_ip:
            return cf_ip.strip()
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def request_fingerprints(request) -> tuple[str, str]:
    return keyed_hash(client_ip(request)), keyed_hash(request.META.get("HTTP_USER_AGENT", "unknown")[:500])


def encrypt_value(value: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.MFA_ENCRYPTION_KEY.encode()).digest())
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt_value(value: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.MFA_ENCRYPTION_KEY.encode()).digest())
    return Fernet(key).decrypt(value.encode()).decode()


def new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, sha256_text(raw)


def make_otp_hash(code: str) -> str:
    return make_password(code)


def verify_otp(code: str, encoded: str) -> bool:
    return bool(encoded) and check_password(code, encoded)


def audit(*, action: str, object_type: str, object_id, actor_type: str, actor_reference: str = "", metadata=None):
    AuditEvent.objects.create(
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        actor_type=actor_type,
        actor_reference_hash=keyed_hash(actor_reference) if actor_reference else "",
        metadata=metadata or {},
    )


def throttle(request, action: str, identity: str, *, limit: int, window_seconds: int, lock_seconds: int) -> bool:
    now = timezone.now()
    key_hash = keyed_hash(f"{client_ip(request)}:{identity.casefold()}")
    with transaction.atomic():
        bucket, _ = ThrottleBucket.objects.select_for_update().get_or_create(
            key_hash=key_hash, action=action
        )
        if bucket.locked_until and bucket.locked_until > now:
            return False
        if now - bucket.window_started_at > timedelta(seconds=window_seconds):
            bucket.count = 0
            bucket.window_started_at = now
            bucket.locked_until = None
        bucket.count += 1
        if bucket.count > limit:
            bucket.locked_until = now + timedelta(seconds=lock_seconds)
        bucket.save(update_fields=["count", "window_started_at", "locked_until"])
        return bucket.locked_until is None


def reset_throttle(request, action: str, identity: str):
    key_hash = keyed_hash(f"{client_ip(request)}:{identity.casefold()}")
    ThrottleBucket.objects.filter(key_hash=key_hash, action=action).delete()


def staff_mfa_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect("staff_login")
        verified = request.session.get("mfa_verified_at")
        verified_user = request.session.get("mfa_verified_user_id")
        if not verified or verified_user != request.user.pk:
            logout(request)
            return redirect("staff_login")
        try:
            verified_at = timezone.datetime.fromisoformat(verified)
            if timezone.is_naive(verified_at):
                verified_at = timezone.make_aware(verified_at)
        except (TypeError, ValueError):
            logout(request)
            return redirect("staff_login")
        if timezone.now() - verified_at > timedelta(minutes=30):
            logout(request)
            return redirect("staff_login")
        return view(request, *args, **kwargs)

    return wrapped


def owner_required(view):
    @staff_mfa_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        profile = getattr(request.user, "staff_profile", None)
        if not profile or profile.role != "owner":
            return HttpResponseForbidden("Owner access is required.")
        return view(request, *args, **kwargs)

    return wrapped
