from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Professor
from app.models.payout import ProfessorSalaryPayment, SalaryPaymentMethod
from app.models.user import User
from app.services.email_branding import render_branded_email
from app.services.i18n import normalize_language
from app.services.notifications.application.orchestrator import OrchestratedNotification
from app.services.notifications.domain.constants import (
    CHANNEL_EMAIL,
    DISPATCH_MODE_IMMEDIATE,
    NOTIFICATION_STATUS_PENDING,
    NOTIFICATION_TYPE_COLLABORATOR_PAYMENT_CONFIRMATION,
    QUEUE_NOTIFICATIONS_IMMEDIATE,
    SOURCE_ADMIN_BO,
)
from app.services.notifications.infrastructure.repository import create_notification_if_new


@dataclass(frozen=True)
class CollaboratorPaymentEmail:
    subject: str
    body: str


def _money_label(amount: Decimal, currency_code: str, *, language: str) -> str:
    normalized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    separator = "," if language == "fr" else "."
    amount_label = f"{normalized:,.2f}"
    if language == "fr":
        amount_label = amount_label.replace(",", " ").replace(".", separator)
    return f"{amount_label} {currency_code.strip().upper() or 'EUR'}"


def _payment_method_label(method: SalaryPaymentMethod, *, language: str) -> str:
    labels = {
        "fr": {
            SalaryPaymentMethod.BANK_TRANSFER: "Virement bancaire",
            SalaryPaymentMethod.CHEQUE: "Chèque",
            SalaryPaymentMethod.CASH: "Espèces",
        },
        "en": {
            SalaryPaymentMethod.BANK_TRANSFER: "Bank transfer",
            SalaryPaymentMethod.CHEQUE: "Cheque",
            SalaryPaymentMethod.CASH: "Cash",
        },
    }
    return labels[language][method]


def build_collaborator_payment_confirmation_email(
    *,
    professor: Professor,
    payment: ProfessorSalaryPayment,
    language: str | None,
) -> CollaboratorPaymentEmail:
    resolved_language = normalize_language(language) or "fr"
    full_name = " ".join(part for part in (professor.first_name, professor.last_name) if part).strip()
    amount_label = _money_label(
        Decimal(payment.amount_incl_vat),
        payment.currency_code,
        language=resolved_language,
    )
    date_label = payment.payment_date.strftime("%d/%m/%Y")
    method_label = _payment_method_label(payment.payment_method, language=resolved_language)

    if resolved_language == "en":
        subject = f"Payment of your invoice {payment.invoice_number}"
        body = render_branded_email(
            preview=f"Your invoice {payment.invoice_number} has been paid.",
            eyebrow="INVOICE PAYMENT",
            title="Payment confirmed",
            greeting=f"Hello {professor.first_name or full_name},",
            intro="We confirm that payment of your invoice has been completed.",
            rows=[
                ("Invoice", payment.invoice_number),
                ("Amount paid (incl. VAT)", amount_label),
                ("Payment date", date_label),
                ("Payment method", method_label),
            ],
            message="No action is required on your part.",
            footer="This email was sent automatically by Piano Académie.",
        )
    else:
        subject = f"Paiement de votre facture {payment.invoice_number}"
        body = render_branded_email(
            preview=f"Votre facture {payment.invoice_number} a été réglée.",
            eyebrow="RÈGLEMENT DE FACTURE",
            title="Paiement confirmé",
            greeting=f"Bonjour {professor.first_name or full_name},",
            intro="Nous vous confirmons que le règlement de votre facture a été effectué.",
            rows=[
                ("Facture", payment.invoice_number),
                ("Montant réglé (TTC)", amount_label),
                ("Date de paiement", date_label),
                ("Mode de règlement", method_label),
            ],
            message="Aucune action n’est requise de votre part.",
        )
    return CollaboratorPaymentEmail(subject=subject, body=body)


def schedule_collaborator_payment_confirmation(
    db: Session,
    *,
    professor: Professor,
    payment: ProfessorSalaryPayment,
) -> list[OrchestratedNotification]:
    recipient_email = (professor.email or "").strip().lower()
    if not recipient_email:
        return []

    recipient = db.scalar(
        select(User).where(func.lower(User.email) == recipient_email).limit(1)
    )
    rendered = build_collaborator_payment_confirmation_email(
        professor=professor,
        payment=payment,
        language=recipient.preferred_language if recipient is not None else "fr",
    )
    idempotency_key = f"collaborator-payment:{payment.id}:confirmation:{recipient_email}"
    created = create_notification_if_new(
        db,
        notification_type=NOTIFICATION_TYPE_COLLABORATOR_PAYMENT_CONFIRMATION,
        channel=CHANNEL_EMAIL,
        dispatch_mode=DISPATCH_MODE_IMMEDIATE,
        source_event_id=None,
        source=SOURCE_ADMIN_BO,
        related_entity_type="professor_salary_payment",
        related_entity_id=payment.id,
        booking_id=None,
        slot_id=None,
        recipient_type="PROFESSOR",
        recipient_contact_id=recipient.id if recipient is not None else None,
        recipient_email=recipient_email,
        recipient_phone=None,
        subject=rendered.subject,
        body_snapshot=rendered.body,
        payload_snapshot={
            "body_format": "HTML",
            "professor_id": str(professor.id),
            "payment_id": str(payment.id),
            "invoice_number": payment.invoice_number,
        },
        idempotency_key=idempotency_key,
        scheduled_for=payment.created_at,
        status=NOTIFICATION_STATUS_PENDING,
    )
    if created is None:
        return []
    return [
        OrchestratedNotification(
            notification_id=created.id,
            queue_name=QUEUE_NOTIFICATIONS_IMMEDIATE,
        )
    ]


__all__ = [
    "CollaboratorPaymentEmail",
    "build_collaborator_payment_confirmation_email",
    "schedule_collaborator_payment_confirmation",
]
