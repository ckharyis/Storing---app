import base64
import binascii
import io
import re
from decimal import Decimal

from PIL import Image, ImageChops
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Contract, LoanApplication


class ApplicationForm(forms.ModelForm):
    accept_terms = forms.BooleanField(label="I have read and accept the application terms.")
    accept_privacy = forms.BooleanField(label="I understand how my personal data will be used.")
    demo_data_confirmed = forms.BooleanField(
        required=False,
        label="I confirm that I am using fictional information in this demonstration.",
    )

    class Meta:
        model = LoanApplication
        fields = ("full_name", "email", "requested_amount", "applicant_note")
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "requested_amount": forms.NumberInput(attrs={"min": "50", "step": "0.01"}),
            "applicant_note": forms.Textarea(attrs={"rows": 4, "placeholder": "Optional context for the reviewer"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.DEMO_MODE:
            self.fields.pop("demo_data_confirmed", None)

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if len(name) < 3 or not re.search(r"[A-Za-zÀ-ÿ]", name):
            raise ValidationError("Enter your full legal name.")
        return name

    def clean_requested_amount(self):
        amount = self.cleaned_data["requested_amount"]
        if amount < settings.MIN_LOAN_AMOUNT or amount > settings.MAX_LOAN_AMOUNT:
            raise ValidationError(
                f"The requested amount must be between XCG {settings.MIN_LOAN_AMOUNT} and XCG {settings.MAX_LOAN_AMOUNT}."
            )
        return amount

    def clean(self):
        cleaned = super().clean()
        if settings.DEMO_MODE and not cleaned.get("demo_data_confirmed"):
            self.add_error("demo_data_confirmed", "Use fictional data only while the portal is in demo mode.")
        return cleaned


class StaffLoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class MFAForm(forms.Form):
    code = forms.CharField(
        min_length=6,
        max_length=24,
        label="Authenticator or recovery code",
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )


class ContractForm(forms.ModelForm):
    legal_review_confirmed = forms.BooleanField(
        label="I confirm the lender identity, pricing and contract wording have been legally reviewed."
    )

    class Meta:
        model = Contract
        fields = (
            "principal",
            "interest_amount",
            "total_repayment",
            "apr_percent",
            "term_months",
            "first_payment_date",
            "daily_late_fee",
            "lender_signatory_name",
        )
        widgets = {"first_payment_date": forms.DateInput(attrs={"type": "date"})}

    def clean_apr_percent(self):
        apr = self.cleaned_data["apr_percent"]
        if apr > settings.MAX_APR:
            raise ValidationError(f"APR cannot exceed the configured maximum of {settings.MAX_APR}%.")
        return apr

    def clean_first_payment_date(self):
        due = self.cleaned_data["first_payment_date"]
        if due <= timezone.localdate():
            raise ValidationError("The first payment date must be in the future.")
        return due

    def clean(self):
        cleaned = super().clean()
        principal = cleaned.get("principal")
        interest = cleaned.get("interest_amount")
        total = cleaned.get("total_repayment")
        if principal is not None and interest is not None and total is not None:
            if total != principal + interest:
                self.add_error("total_repayment", "Total repayment must equal principal plus interest.")
        return cleaned


class OTPForm(forms.Form):
    code = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )


class SignatureForm(forms.Form):
    typed_name = forms.CharField(max_length=160, label="Type your full legal name")
    signature_data = forms.CharField(widget=forms.HiddenInput())
    accept_contract = forms.BooleanField(
        label="I have reviewed the complete agreement and agree to be legally bound by its terms."
    )
    confirm_copy = forms.BooleanField(label="I understand that I can download and keep a copy of the agreement.")

    def __init__(self, *args, expected_name: str, **kwargs):
        self.expected_name = " ".join(expected_name.split()).casefold()
        super().__init__(*args, **kwargs)

    def clean_typed_name(self):
        value = " ".join(self.cleaned_data["typed_name"].split())
        if value.casefold() != self.expected_name:
            raise ValidationError("The typed name must match the applicant name exactly.")
        return value

    def clean_signature_data(self):
        value = self.cleaned_data["signature_data"]
        prefix = "data:image/png;base64,"
        if not value.startswith(prefix):
            raise ValidationError("Draw your signature in the signature box.")
        try:
            raw = base64.b64decode(value[len(prefix) :], validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError("The signature image is invalid.")
        if len(raw) > 1024 * 1024:
            raise ValidationError("The signature image is too large.")
        try:
            opened = Image.open(io.BytesIO(raw))
            opened.verify()
            image = Image.open(io.BytesIO(raw)).convert("RGBA")
            if image.width > 1600 or image.height > 800 or image.width < 100 or image.height < 50:
                raise ValidationError("The signature image dimensions are invalid.")
            background = Image.new("RGBA", image.size, (0, 0, 0, 0))
            if ImageChops.difference(image, background).getbbox() is None:
                raise ValidationError("Draw your signature before continuing.")
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("The signature image could not be verified.")
        self.signature_bytes = raw
        return value
