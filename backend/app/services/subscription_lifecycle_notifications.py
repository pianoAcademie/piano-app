from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.plan import ClientPlanSubscription, Plan
from app.models.user import User
from app.services.email_delivery import send_email
from app.services.i18n import normalize_language
from app.services.messaging_templates import resolve_frontend_base_url, resolve_sender_profile
from app.services.notifications.application.recipients import resolve_admin_plan_purchase_recipients

logger = logging.getLogger(__name__)


def _display_name(user: User) -> str:
    return " ".join(part for part in ((user.first_name or "").strip(), (user.last_name or "").strip()) if part) or user.email


def _frontend_url(path: str) -> str:
    base = resolve_frontend_base_url().strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base + path


def _send_client_email(
    db: Session,
    *,
    client: User,
    subject_fr: str,
    subject_en: str,
    body_fr: str,
    body_en: str,
    context: str,
) -> str | None:
    if not (client.email or "").strip():
        return None
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    english = normalize_language(client.preferred_language) == "en"
    try:
        return send_email(
            to_email=client.email,
            subject=subject_en if english else subject_fr,
            body=body_en if english else body_fr,
            body_format="TEXT",
            context=context,
            from_email=sender.from_email,
            from_name=sender.from_name,
            reply_to=sender.reply_to,
            subject_prefix=sender.subject_prefix,
            recipient_user_id=client.id,
        )
    except Exception:
        logger.exception("Unable to send subscription lifecycle email context=%s client=%s", context, client.id)
        return None


def send_cancellation_request_admin_notifications(
    db: Session,
    *,
    client: User,
    plan: Plan,
    subscription: ClientPlanSubscription,
    requested_at: datetime,
    note: str | None,
) -> list[str]:
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    client_name = _display_name(client)
    subject = f"Demande de resiliation a valider - {client_name}"
    body = (
        "Une demande de resiliation a ete envoyee depuis l'espace client.\n\n"
        f"Client : {client_name} ({client.email})\n"
        f"Abonnement : {plan.name}\n"
        f"Reference : {subscription.id}\n"
        f"Date de demande : {requested_at.astimezone().strftime('%d/%m/%Y %H:%M')}\n"
        f"Message du client : {(note or '-').strip() or '-'}\n\n"
        f"Valider ou refuser la demande : {_frontend_url(f'/admin/clients/{client.id}?tab=fiche')}"
    )
    sent: list[str] = []
    seen: set[str] = set()
    for recipient in resolve_admin_plan_purchase_recipients(db):
        email = (recipient.email or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        try:
            message_id = send_email(
                to_email=email,
                subject=subject,
                body=body,
                context="SUBSCRIPTION_CANCELLATION_REQUEST_ADMIN",
                from_email=sender.from_email,
                from_name=sender.from_name,
                reply_to=sender.reply_to,
                subject_prefix=sender.subject_prefix,
            )
            if message_id:
                sent.append(message_id)
        except Exception:
            logger.exception("Unable to notify admin of cancellation request subscription=%s", subscription.id)
    return sent


def send_cancellation_decision_email(
    db: Session,
    *,
    client: User,
    plan: Plan,
    approved: bool,
    effective_at: datetime | None,
) -> str | None:
    name = _display_name(client)
    if approved and effective_at is not None:
        local_effective_at = effective_at.astimezone(ZoneInfo("Europe/Paris"))
        effective_fr = local_effective_at.strftime("%d/%m/%Y")
        effective_en = local_effective_at.strftime("%Y-%m-%d")
        return _send_client_email(
            db,
            client=client,
            subject_fr=f"Confirmation de resiliation - {plan.name}",
            subject_en=f"Cancellation confirmed - {plan.name}",
            body_fr=(
                f"Bonjour {name},\n\nVotre demande de resiliation de l'abonnement « {plan.name} » a ete validee. "
                f"Elle prendra effet juste avant l'echeance du {effective_fr}. Aucun nouveau paiement ne sera preleve a cette echeance.\n\n"
                "Vous conservez vos acces jusqu'a cette date.\n\nCordialement,\nL'equipe Piano Academie"
            ),
            body_en=(
                f"Hello {name},\n\nYour request to cancel the “{plan.name}” subscription has been approved. "
                f"It will take effect immediately before the {effective_en} renewal. No new payment will be collected on that date.\n\n"
                "You retain access until then.\n\nKind regards,\nThe Piano Academie team"
            ),
            context="SUBSCRIPTION_CANCELLATION_APPROVED_CLIENT",
        )
    return _send_client_email(
        db,
        client=client,
        subject_fr=f"Suivi de votre demande de resiliation - {plan.name}",
        subject_en=f"Update on your cancellation request - {plan.name}",
        body_fr=(
            f"Bonjour {name},\n\nVotre demande de resiliation de l'abonnement « {plan.name} » n'a pas ete validee. "
            "Votre abonnement reste actif. Pour toute question, contactez l'ecole au 01 86 47 60 88.\n\n"
            "Cordialement,\nL'equipe Piano Academie"
        ),
        body_en=(
            f"Hello {name},\n\nYour request to cancel the “{plan.name}” subscription was not approved. "
            "Your subscription remains active. If you have any questions, contact the school on +33 1 86 47 60 88.\n\n"
            "Kind regards,\nThe Piano Academie team"
        ),
        context="SUBSCRIPTION_CANCELLATION_REJECTED_CLIENT",
    )


def send_suspension_confirmation_email(
    db: Session,
    *,
    client: User,
    plan: Plan,
    start_date: date,
    end_date: date,
) -> str | None:
    name = _display_name(client)
    resume_date = date.fromordinal(end_date.toordinal() + 1)
    return _send_client_email(
        db,
        client=client,
        subject_fr=f"Confirmation de mise en pause - {plan.name}",
        subject_en=f"Subscription pause confirmed - {plan.name}",
        body_fr=(
            f"Bonjour {name},\n\nVotre abonnement « {plan.name} » sera mis en pause du {start_date.strftime('%d/%m/%Y')} "
            f"au {end_date.strftime('%d/%m/%Y')} inclus. Vous pourrez reprendre vos cours des le {resume_date.strftime('%d/%m/%Y')}.\n\n"
            "Votre prochaine echeance a ete decalee de la duree de la pause.\n\nCordialement,\nL'equipe Piano Academie"
        ),
        body_en=(
            f"Hello {name},\n\nYour “{plan.name}” subscription will be paused from {start_date.strftime('%Y-%m-%d')} "
            f"through {end_date.strftime('%Y-%m-%d')}, inclusive. You can resume lessons on {resume_date.strftime('%Y-%m-%d')}.\n\n"
            "Your next renewal has been postponed by the length of the pause.\n\nKind regards,\nThe Piano Academie team"
        ),
        context="SUBSCRIPTION_PAUSE_CONFIRMED_CLIENT",
    )


__all__ = [
    "send_cancellation_decision_email",
    "send_cancellation_request_admin_notifications",
    "send_suspension_confirmation_email",
]
