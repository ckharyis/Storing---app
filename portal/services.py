import calendar
import hashlib
import io
import secrets
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .contract_templates.loan_agreement_nl_v1 import CLAUSES, agreement_snapshot
from .models import Contract, SigningSession
from .security import make_otp_hash, new_token


MONEY = Decimal("0.01")


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_schedule(total: Decimal, months: int, first_due: date) -> list[dict]:
    regular = (total / Decimal(months)).quantize(MONEY, rounding=ROUND_HALF_UP)
    remaining = total
    rows = []
    for index in range(months):
        amount = regular if index < months - 1 else remaining
        remaining -= amount
        rows.append({"number": index + 1, "due_date": add_months(first_due, index).isoformat(), "amount": f"{amount:.2f}"})
    return rows


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ContractTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="ContractMeta", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#50627A")))
    styles.add(ParagraphStyle(name="ContractHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#15375B"), spaceBefore=7, spaceAfter=3))
    styles.add(ParagraphStyle(name="ContractBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12.5, alignment=TA_LEFT, spaceAfter=6))
    styles.add(ParagraphStyle(name="Warning", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#8A2D12"), backColor=colors.HexColor("#FFF1E8"), borderColor=colors.HexColor("#F2B38C"), borderWidth=0.5, borderPadding=6, spaceAfter=10))
    return styles


def render_contract_pdf(contract: Contract, signature_bytes: bytes | None = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="Overeenkomst onderhandse lening")
    styles = _styles()
    story = [Paragraph("Overeenkomst onderhandse lening", styles["ContractTitle"])]
    if settings.DEMO_MODE:
        story.append(Paragraph("DEMO - NIET VOOR ECHTE AANVRAGEN - JURIDISCHE CONTROLE VEREIST", styles["Warning"]))

    story.extend(
        [
            Paragraph(f"Contractversie: {contract.template_version}", styles["ContractMeta"]),
            Paragraph(f"Aanvraagreferentie: {contract.application.reference}", styles["ContractMeta"]),
            Spacer(1, 6),
            Paragraph("Partijen", styles["ContractHeading"]),
            Paragraph(
                f"Schuldeiser: {settings.BUSINESS_LEGAL_NAME}, gevestigd te {settings.BUSINESS_ADDRESS}, "
                f"registratienummer {settings.BUSINESS_REGISTRATION_NUMBER}, autorisatiereferentie "
                f"{settings.LENDER_AUTHORIZATION_REFERENCE}; en schuldenaar: {contract.application.full_name}, "
                f"gezamenlijk te noemen 'partijen'.",
                styles["ContractBody"],
            ),
            Paragraph("Financiële kerngegevens", styles["ContractHeading"]),
        ]
    )

    financial_rows = [
        ["Hoofdsom", f"XCG {contract.principal:.2f}"],
        ["Rente", f"XCG {contract.interest_amount:.2f}"],
        ["Totale terugbetaling", f"XCG {contract.total_repayment:.2f}"],
        ["Vermeld APR", f"{contract.apr_percent:.2f}%"],
        ["Looptijd", f"{contract.term_months} maand(en)"],
        ["Dagelijkse vergoeding bij te late betaling", f"XCG {contract.daily_late_fee:.2f}"],
    ]
    finance_table = Table(financial_rows, colWidths=[88 * mm, 78 * mm])
    finance_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F4F7FA")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCD7E3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE5ED")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([finance_table, Paragraph("Betalingsschema", styles["ContractHeading"])])
    schedule_rows = [["Termijn", "Vervaldatum", "Bedrag"]] + [
        [str(row["number"]), row["due_date"], f"XCG {row['amount']}"] for row in contract.installment_schedule
    ]
    schedule = Table(schedule_rows, colWidths=[35 * mm, 65 * mm, 66 * mm], repeatRows=1)
    schedule.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#15375B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCD7E3")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(schedule)

    for title, text in CLAUSES:
        story.extend([Paragraph(title, styles["ContractHeading"]), Paragraph(text, styles["ContractBody"])])

    story.extend(
        [
            Paragraph("Toepasselijk recht en bevestiging", styles["ContractHeading"]),
            Paragraph(
                "Op deze overeenkomst is het recht van Curaçao van toepassing. De schuldenaar bevestigt de "
                "overeenkomst vóór ondertekening te hebben kunnen lezen, opslaan en controleren.",
                styles["ContractBody"],
            ),
            Spacer(1, 10),
        ]
    )
    if signature_bytes:
        story.append(Paragraph("Elektronische ondertekening", styles["ContractHeading"]))
        signature = Image(io.BytesIO(signature_bytes), width=62 * mm, height=24 * mm)
        sign_table = Table(
            [
                [signature, Paragraph(f"Namens schuldeiser:<br/><b>{contract.lender_signatory_name}</b>", styles["ContractBody"])],
                [Paragraph(f"Schuldenaar:<br/><b>{contract.application.full_name}</b>", styles["ContractBody"]), Paragraph(f"Geaccepteerd op:<br/><b>{timezone.localtime(contract.signed_at):%d-%m-%Y %H:%M %Z}</b>", styles["ContractBody"])],
            ],
            colWidths=[83 * mm, 83 * mm],
        )
        sign_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCD7E3")), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDE5ED")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 7)]))
        story.append(sign_table)
        story.append(Spacer(1, 18))
        story.append(Paragraph("Ondertekeningsbewijs", styles["ContractTitle"]))
        evidence = contract.signature_evidence
        evidence_rows = [
            ["Ondertekenaar", evidence.signer_typed_name],
            ["Geverifieerd e-mailadres", evidence.signer_email],
            ["Tijdstip", timezone.localtime(evidence.agreed_at).isoformat()],
            ["Contract-hash vóór ondertekening", evidence.document_hash_at_signing],
            ["Toestemmingsversie", evidence.consent_text_version],
            ["Auditreferentie", str(contract.id)],
        ]
        evidence_table = Table(evidence_rows, colWidths=[58 * mm, 108 * mm])
        evidence_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCD7E3")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F7FA")), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5)]))
        story.append(evidence_table)
    else:
        story.append(Paragraph(f"Namens schuldeiser elektronisch voorbereid door: {contract.lender_signatory_name}", styles["ContractBody"]))
        story.append(Paragraph("Handtekening schuldenaar: nog niet geplaatst", styles["ContractBody"]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DDE5ED"))
        canvas.line(19 * mm, 11 * mm, A4[0] - 19 * mm, 11 * mm)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(19 * mm, 7 * mm, f"Referentie {contract.application.reference}")
        canvas.drawRightString(A4[0] - 19 * mm, 7 * mm, f"Pagina {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def save_draft_pdf(contract: Contract):
    pdf = render_contract_pdf(contract)
    contract.draft_document_hash = hashlib.sha256(pdf).hexdigest()
    contract.draft_pdf.save(f"contract-{contract.id}-draft.pdf", ContentFile(pdf), save=False)
    contract.save(update_fields=["draft_pdf", "draft_document_hash", "updated_at"])


def save_final_pdf(contract: Contract, signature_bytes: bytes):
    pdf = render_contract_pdf(contract, signature_bytes=signature_bytes)
    contract.final_document_hash = hashlib.sha256(pdf).hexdigest()
    contract.final_pdf.save(f"contract-{contract.id}-signed.pdf", ContentFile(pdf), save=False)
    contract.save(update_fields=["final_pdf", "final_document_hash", "updated_at"])


def create_signing_session(contract: Contract) -> tuple[SigningSession, str]:
    contract.signing_sessions.filter(consumed_at__isnull=True).update(consumed_at=timezone.now())
    raw, token_hash = new_token()
    session = SigningSession.objects.create(contract=contract, token_hash=token_hash, expires_at=SigningSession.expiry())
    return session, raw


def send_signing_email(contract: Contract, raw_token: str):
    url = f"{settings.SITE_BASE_URL}{reverse('sign_contract', kwargs={'token': raw_token})}"
    send_mail(
        subject=f"Agreement ready - {contract.application.reference}",
        message=(
            f"Hello {contract.application.full_name},\n\nYour loan agreement is ready for review. "
            f"Open this secure link within seven days:\n{url}\n\nDo not forward this link. You will receive a separate verification code before signing."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contract.application.email],
        fail_silently=False,
    )


def issue_signing_otp(session: SigningSession) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    session.otp_hash = make_otp_hash(code)
    session.otp_expires_at = timezone.now() + timedelta(minutes=10)
    session.otp_attempts = 0
    session.otp_verified_at = None
    session.save(update_fields=["otp_hash", "otp_expires_at", "otp_attempts", "otp_verified_at"])
    send_mail(
        subject="Your signing verification code",
        message=f"Your one-time verification code is {code}. It expires in 10 minutes. Do not share it.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[session.contract.application.email],
        fail_silently=False,
    )
    return code
