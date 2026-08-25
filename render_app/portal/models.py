import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def new_reference() -> str:
    return f"LN-{timezone.localdate():%Y%m}-{secrets.token_hex(3).upper()}"


def private_upload_path(instance, filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"private/{timezone.localdate():%Y/%m}/{uuid.uuid4().hex}.{suffix}"


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        REVIEW = "review", "Under review"
        MORE_INFO = "more_info", "More information required"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"
        CONTRACT_SENT = "contract_sent", "Contract sent"
        SIGNED = "signed", "Signed"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=24, unique=True, default=new_reference, editable=False)
    full_name = models.CharField(max_length=160)
    email = models.EmailField()
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    applicant_note = models.TextField(blank=True, max_length=1000)
    terms_version = models.CharField(max_length=60)
    privacy_version = models.CharField(max_length=60)
    terms_accepted_at = models.DateTimeField()
    privacy_accepted_at = models.DateTimeField()
    submitted_ip_hash = models.CharField(max_length=64)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    is_demo = models.BooleanField(default=True)
    retention_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"]), models.Index(fields=["email"])]

    def __str__(self):
        return f"{self.reference} - {self.full_name}"

    @property
    def masked_email(self):
        local, _, domain = self.email.partition("@")
        visible = local[:2] if len(local) > 2 else local[:1]
        return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


class StaffProfile(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        REVIEWER = "reviewer", "Reviewer"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.REVIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class AdminMFADevice(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mfa_device")
    encrypted_secret = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    last_used_step = models.BigIntegerField(default=-1)
    created_at = models.DateTimeField(auto_now_add=True)


class Contract(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent for signature"
        SIGNED = "signed", "Signed"
        VOID = "void", "Void"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(LoanApplication, on_delete=models.PROTECT, related_name="contracts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    template_version = models.CharField(max_length=80)
    agreement_text_snapshot = models.TextField()
    principal = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    total_repayment = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    apr_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("27.00"))],
    )
    term_months = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(24)])
    first_payment_date = models.DateField()
    daily_late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    installment_schedule = models.JSONField(default=list)
    lender_signatory_name = models.CharField(max_length=160)
    lender_accepted_at = models.DateTimeField()
    draft_pdf = models.FileField(upload_to=private_upload_path, blank=True)
    final_pdf = models.FileField(upload_to=private_upload_path, blank=True)
    draft_document_hash = models.CharField(max_length=64, blank=True)
    final_document_hash = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_contracts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Contract {str(self.id)[:8]} for {self.application.reference}"


class SigningSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="signing_sessions")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    otp_hash = models.CharField(max_length=128, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def active(self):
        return self.consumed_at is None and self.expires_at > timezone.now()

    @classmethod
    def expiry(cls):
        return timezone.now() + timedelta(days=7)


class SignatureEvidence(models.Model):
    contract = models.OneToOneField(Contract, on_delete=models.PROTECT, related_name="signature_evidence")
    signature_image = models.FileField(upload_to=private_upload_path)
    signer_typed_name = models.CharField(max_length=160)
    signer_email = models.EmailField()
    agreed_at = models.DateTimeField()
    document_hash_at_signing = models.CharField(max_length=64)
    ip_hash = models.CharField(max_length=64)
    user_agent_hash = models.CharField(max_length=64)
    consent_text_version = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_type = models.CharField(max_length=30)
    actor_reference_hash = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=40)
    object_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id", "created_at"])]


class ThrottleBucket(models.Model):
    key_hash = models.CharField(max_length=64)
    action = models.CharField(max_length=40)
    count = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key_hash", "action"], name="unique_throttle_bucket")]
