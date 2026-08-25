import base64
import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

import pyotp
from PIL import Image, ImageDraw
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from portal.contract_templates.loan_agreement_nl_v1 import agreement_snapshot
from portal.forms import ContractForm
from portal.models import Contract, LoanApplication, SignatureEvidence, StaffProfile
from portal.services import build_schedule, create_signing_session, issue_signing_otp, save_draft_pdf


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PortalFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="lending-portal-tests-")
        self.override_media = override_settings(MEDIA_ROOT=self.media_root)
        self.override_media.enable()

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def make_application(self, status=LoanApplication.Status.APPROVED):
        now = timezone.now()
        return LoanApplication.objects.create(
            full_name="Demo Applicant",
            email="demo.applicant@example.com",
            requested_amount=Decimal("300.00"),
            status=status,
            terms_version="test-terms",
            privacy_version="test-privacy",
            terms_accepted_at=now,
            privacy_accepted_at=now,
            submitted_ip_hash="a" * 64,
            user_agent_hash="b" * 64,
            is_demo=True,
            retention_until=timezone.localdate() + timedelta(days=365),
        )

    def make_contract(self, application, user):
        contract = Contract.objects.create(
            application=application,
            template_version="test-template",
            agreement_text_snapshot=agreement_snapshot(),
            principal=Decimal("300.00"),
            interest_amount=Decimal("30.00"),
            total_repayment=Decimal("330.00"),
            apr_percent=Decimal("20.00"),
            term_months=2,
            first_payment_date=timezone.localdate() + timedelta(days=30),
            daily_late_fee=Decimal("0.00"),
            installment_schedule=build_schedule(Decimal("330.00"), 2, timezone.localdate() + timedelta(days=30)),
            lender_signatory_name="Demo Reviewer",
            lender_accepted_at=timezone.now(),
            created_by=user,
        )
        save_draft_pdf(contract)
        contract.refresh_from_db()
        return contract

    def signature_data(self):
        image = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.line((80, 190, 280, 80, 520, 200, 780, 95), fill=(16, 36, 61, 255), width=9)
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def test_home_has_security_headers(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_application_requires_demo_confirmation_and_records_consent(self):
        payload = {
            "full_name": "Demo Applicant",
            "email": "Demo.Applicant@Example.com",
            "requested_amount": "300.00",
            "applicant_note": "Fictional test request.",
            "accept_terms": "on",
            "accept_privacy": "on",
        }
        response = self.client.post(reverse("apply"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use fictional data only")
        payload["demo_data_confirmed"] = "on"
        response = self.client.post(reverse("apply"), payload)
        self.assertRedirects(response, reverse("application_success"), fetch_redirect_response=False)
        application = LoanApplication.objects.get()
        self.assertEqual(application.email, "demo.applicant@example.com")
        self.assertTrue(application.is_demo)
        self.assertIsNotNone(application.terms_accepted_at)

    def test_admin_password_is_not_enough_without_mfa(self):
        user = User.objects.create_user("reviewer", "reviewer@example.com", "A-strong-demo-password-123")
        user.is_staff = True
        user.save()
        StaffProfile.objects.create(user=user, role=StaffProfile.Role.OWNER)
        response = self.client.post(reverse("staff_login"), {"username": "reviewer", "password": "A-strong-demo-password-123"})
        self.assertRedirects(response, reverse("staff_mfa_setup"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.get(reverse("staff_mfa_setup"))
        secret = self.client.session["mfa_setup_secret"]
        response = self.client.post(reverse("staff_mfa_setup"), {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(response, reverse("staff_recovery_codes"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 200)

    def test_contract_form_blocks_configured_apr_ceiling(self):
        form = ContractForm(
            data={
                "principal": "300.00",
                "interest_amount": "60.00",
                "total_repayment": "360.00",
                "apr_percent": "27.01",
                "term_months": "2",
                "first_payment_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
                "daily_late_fee": "0.00",
                "lender_signatory_name": "Demo Reviewer",
                "legal_review_confirmed": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("apr_percent", form.errors)

    def test_email_otp_signature_creates_final_pdf_and_evidence(self):
        user = User.objects.create_user("owner", "owner@example.com", "A-strong-demo-password-123")
        application = self.make_application()
        contract = self.make_contract(application, user)
        self.assertTrue(contract.draft_pdf.name)
        with contract.draft_pdf.open("rb") as draft:
            self.assertEqual(draft.read(4), b"%PDF")

        session, raw = create_signing_session(contract)
        code = issue_signing_otp(session)
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(reverse("sign_contract", args=[raw]), {"action": "verify_otp", "code": code})
        self.assertRedirects(response, reverse("sign_contract", args=[raw]), fetch_redirect_response=False)
        response = self.client.post(
            reverse("sign_contract", args=[raw]),
            {
                "action": "sign",
                "typed_name": "Demo Applicant",
                "signature_data": self.signature_data(),
                "accept_contract": "on",
                "confirm_copy": "on",
            },
        )
        self.assertRedirects(response, reverse("sign_contract", args=[raw]), fetch_redirect_response=False)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.SIGNED)
        self.assertTrue(contract.final_pdf.name)
        self.assertEqual(SignatureEvidence.objects.filter(contract=contract).count(), 1)
        with contract.final_pdf.open("rb") as final:
            self.assertEqual(final.read(4), b"%PDF")

    def test_unknown_signing_token_is_not_disclosed(self):
        response = self.client.get(reverse("sign_contract", args=["not-a-real-token"]))
        self.assertEqual(response.status_code, 404)

    def test_draft_pdf_requires_email_verification(self):
        user = User.objects.create_user("owner2", "owner2@example.com", "A-strong-demo-password-123")
        contract = self.make_contract(self.make_application(), user)
        _, raw = create_signing_session(contract)
        response = self.client.get(reverse("signer_contract_pdf", args=[raw]))
        self.assertEqual(response.status_code, 403)

    def test_reviewer_cannot_create_or_send_contract(self):
        reviewer = User.objects.create_user("reviewer2", "reviewer2@example.com", "A-strong-demo-password-123")
        reviewer.is_staff = True
        reviewer.save()
        StaffProfile.objects.create(user=reviewer, role=StaffProfile.Role.REVIEWER)
        self.client.force_login(reviewer)
        session = self.client.session
        session["mfa_verified_user_id"] = reviewer.pk
        session["mfa_verified_at"] = timezone.now().isoformat()
        session.save()
        application = self.make_application()
        response = self.client.get(reverse("staff_contract_create", args=[application.id]))
        self.assertEqual(response.status_code, 403)
