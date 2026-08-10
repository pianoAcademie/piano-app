from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from html import escape
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
    body_format: str = "TEXT",
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
            body_format=body_format,
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


def _branded_email(
    *,
    preview: str,
    eyebrow: str,
    title: str,
    greeting: str,
    intro: str,
    rows: list[tuple[str, str]],
    message: str,
    footer: str,
) -> str:
    summary_rows = "".join(
        (
            '<tr>'
            f'<td style="padding:8px 12px 8px 20px;width:40%;font-size:13px;font-weight:700;color:#667085;">{escape(label)}</td>'
            f'<td style="padding:8px 20px 8px 12px;font-size:15px;font-weight:700;color:#172033;">{escape(value)}</td>'
            '</tr>'
        )
        for label, value in rows
    )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f2f4f7;">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">'
        f'{escape(preview)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f2f4f7;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="max-width:620px;background:#ffffff;border:1px solid #e3e7ee;border-radius:16px;overflow:hidden;">'
        '<tr><td style="padding:28px 30px;background:#172033;">'
        '<div style="font-size:13px;line-height:18px;font-weight:800;letter-spacing:1.5px;color:#e4b85d;">PIANO ACADÉMIE</div>'
        f'<div style="margin-top:8px;font-size:12px;line-height:18px;font-weight:700;letter-spacing:1px;color:#e4b85d;">{escape(eyebrow)}</div>'
        f'<div style="margin-top:5px;font-size:28px;line-height:35px;font-weight:800;color:#ffffff;">{escape(title)}</div>'
        '</td></tr>'
        '<tr><td style="padding:28px 30px 30px 30px;">'
        f'<p style="margin:0 0 10px 0;font-size:17px;line-height:25px;color:#172033;">{escape(greeting)}</p>'
        f'<p style="margin:0 0 22px 0;font-size:15px;line-height:23px;color:#5f6673;">{escape(intro)}</p>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:0;background:#f8fafc;border:1px solid #e3e7ee;border-radius:12px;">'
        f'{summary_rows}'
        '</table>'
        '<div style="margin:22px 0 0;padding:18px 20px;background:#fff7e6;border:1px solid #edd7b3;border-radius:12px;">'
        f'<p style="margin:0;font-size:15px;line-height:23px;color:#5f4a2d;">{escape(message)}</p>'
        '</div>'
        f'<p style="margin:22px 0 0;font-size:12px;line-height:19px;color:#7b8494;text-align:center;">{escape(footer)}</p>'
        '</td></tr></table>'
        '</td></tr></table></body></html>'
    )


def _french_date(value: date) -> str:
    months = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )
    return f"{value.day} {months[value.month - 1]} {value.year}"


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
    subject = f"Demande de résiliation à valider - {client_name}"
    body = (
        "Une demande de résiliation a été envoyée depuis l’espace client.\n\n"
        f"Client : {client_name} ({client.email})\n"
        f"Abonnement : {plan.name}\n"
        f"Référence : {subscription.id}\n"
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
        effective_date_fr = _french_date(local_effective_at.date())
        effective_date_en = local_effective_at.strftime("%B %-d, %Y")
        effective_at_local_midnight = not any(
            (
                local_effective_at.hour,
                local_effective_at.minute,
                local_effective_at.second,
                local_effective_at.microsecond,
            )
        )
        if effective_at_local_midnight:
            last_access_date = local_effective_at.date() - timedelta(days=1)
            last_access_fr = f"{_french_date(last_access_date)} inclus"
            last_access_en = f"{last_access_date.strftime('%B %-d, %Y')}, inclusive"
            access_fr = f"Vous conservez vos accès jusqu’au {_french_date(last_access_date)} inclus."
            access_en = f"You retain access through {last_access_date.strftime('%B %-d, %Y')}, inclusive."
        else:
            last_access_fr = f"{effective_date_fr} à {local_effective_at.strftime('%H:%M')}"
            last_access_en = f"{effective_date_en} at {local_effective_at.strftime('%H:%M')}"
            access_fr = f"Vous conservez vos accès jusqu’au {last_access_fr}."
            access_en = f"You retain access until {last_access_en}."
        return _send_client_email(
            db,
            client=client,
            subject_fr=f"Confirmation de résiliation - {plan.name}",
            subject_en=f"Cancellation confirmed - {plan.name}",
            body_fr=_branded_email(
                preview=f"Votre résiliation est confirmée. Accès maintenu jusqu’au {last_access_fr}.",
                eyebrow="ABONNEMENT",
                title="Confirmation de résiliation",
                greeting=f"Bonjour {name},",
                intro="Votre demande de résiliation a bien été prise en compte.",
                rows=[
                    ("Abonnement", plan.name),
                    ("Fin de vos accès", last_access_fr),
                    ("Résiliation effective", effective_date_fr),
                    ("Prochain paiement", "Aucun nouveau prélèvement"),
                ],
                message=access_fr,
                footer="Cet e-mail de confirmation a été envoyé automatiquement par Piano Académie.",
            ),
            body_en=_branded_email(
                preview=f"Your cancellation is confirmed. Access remains available through {last_access_en}.",
                eyebrow="SUBSCRIPTION",
                title="Cancellation confirmed",
                greeting=f"Hello {name},",
                intro="Your subscription cancellation has been confirmed.",
                rows=[
                    ("Subscription", plan.name),
                    ("Access available through", last_access_en),
                    ("Cancellation effective", effective_date_en),
                    ("Next payment", "No new payment will be collected"),
                ],
                message=access_en,
                footer="This confirmation email was sent automatically by Piano Academie.",
            ),
            context="SUBSCRIPTION_CANCELLATION_APPROVED_CLIENT",
            body_format="HTML",
        )
    return _send_client_email(
        db,
        client=client,
        subject_fr=f"Suivi de votre demande de résiliation - {plan.name}",
        subject_en=f"Update on your cancellation request - {plan.name}",
        body_fr=(
            f"Bonjour {name},\n\nVotre demande de résiliation de l’abonnement « {plan.name} » n’a pas été validée. "
            "Votre abonnement reste actif. Pour toute question, contactez l’école au 01 86 47 60 88.\n\n"
            "Cordialement,\nL’équipe Piano Académie"
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
            f"au {end_date.strftime('%d/%m/%Y')} inclus. Vous pourrez reprendre vos cours dès le {resume_date.strftime('%d/%m/%Y')}.\n\n"
            "Votre prochaine échéance a été décalée de la durée de la pause.\n\nCordialement,\nL’équipe Piano Académie"
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
