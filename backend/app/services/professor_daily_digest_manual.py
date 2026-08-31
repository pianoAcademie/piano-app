"""On-demand daily planning. Does not change the scheduled job's settings/state."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Professor
from app.models.ops import CommunicationChannel, CommunicationDeliveryStatus, CommunicationLog, CommunicationSenderCategory
from app.models.user import User
from app.schemas.admin import AdminCollaboratorDailyScheduleOut, AdminCollaboratorDailyScheduleRequest
from app.services.email_delivery import send_email
from app.services.professor_daily_digest import PARIS_TIMEZONE, _build_digest_body

MANUAL_DIGEST_SOURCE = "PROFESSOR_DAILY_DIGEST_MANUAL:"


def send_manual_daily_schedule(
    db: Session,
    *,
    professor: Professor,
    actor: User,
    payload: AdminCollaboratorDailyScheduleRequest,
    now: datetime,
) -> AdminCollaboratorDailyScheduleOut:
    # Caller holds the professor row lock until the journal is committed.
    today = now.astimezone(PARIS_TIMEZONE).date()
    if payload.digest_date != today:
        raise HTTPException(409, "La date a changé. Actualisez la fiche pour envoyer le planning du jour.")
    if not professor.active:
        raise HTTPException(409, "Ce collaborateur est inactif. Aucun email envoyé.")
    if payload.recipient.strip().casefold() != professor.email.strip().casefold():
        raise HTTPException(409, "L’adresse email a changé. Actualisez la fiche et confirmez le destinataire.")

    source = f"{MANUAL_DIGEST_SOURCE}{payload.request_id}"
    # Any accepted SMTP send remains consumed even if a later delivery event
    # reports a bounce. A repeated HTTP request must not send it again.
    previous = db.scalar(
        select(CommunicationLog).where(
            CommunicationLog.professor_id == professor.id,
            CommunicationLog.channel == CommunicationChannel.EMAIL,
            CommunicationLog.source == source,
        ).order_by(CommunicationLog.occurred_at.desc()).limit(1)
    )
    if previous:
        if previous.delivery_status in (CommunicationDeliveryStatus.SENT, CommunicationDeliveryStatus.DELIVERED):
            return AdminCollaboratorDailyScheduleOut(
                status="already_sent", digest_date=today, recipient=professor.email,
                message_id=previous.provider_message_id,
            )
        raise HTTPException(409, "Cette tentative est déjà enregistrée. Vérifiez les communications avant un nouvel envoi.")

    recent = db.scalar(
        select(CommunicationLog.id).where(
            CommunicationLog.professor_id == professor.id,
            CommunicationLog.channel == CommunicationChannel.EMAIL,
            CommunicationLog.source.startswith(MANUAL_DIGEST_SOURCE, autoescape=True),
            CommunicationLog.occurred_at >= now - timedelta(seconds=60),
        ).limit(1)
    )
    if recent:
        raise HTTPException(429, "Un renvoi vient d’être demandé. Patientez une minute avant de recommencer.")

    day_start = datetime.combine(today, time.min, tzinfo=PARIS_TIMEZONE)
    day_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=PARIS_TIMEZONE)
    subject, body, count = _build_digest_body(
        db, professor=professor, digest_date=today,
        day_start_utc=day_start.astimezone(timezone.utc),
        day_end_utc=day_end.astimezone(timezone.utc),
    )
    if count == 0:
        return AdminCollaboratorDailyScheduleOut(status="no_courses", digest_date=today, recipient=professor.email)

    message_id = send_email(
        to_email=professor.email, subject=subject, body=body, body_format="HTML",
        context=source, professor_id=professor.id,
        sender_user_id=actor.id,
        sender_label=f"{actor.first_name or ''} {actor.last_name or ''}".strip() or actor.email,
        sender_category=CommunicationSenderCategory.OTHER_USER,
        db=db,
    )
    # Persist successes AND failures before reporting the result. In particular
    # LOG mode/SMTP errors must never produce a success message in the UI.
    db.commit()
    if not message_id:
        raise HTTPException(502, "L’envoi de l’email a échoué. Consultez l’historique des communications.")
    return AdminCollaboratorDailyScheduleOut(
        status="sent", digest_date=today, recipient=professor.email, message_id=message_id,
    )
