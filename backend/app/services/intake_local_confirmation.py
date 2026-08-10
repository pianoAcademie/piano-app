from __future__ import annotations

from datetime import datetime, timezone
import logging
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Professor
from app.models.ops import CommunicationSenderCategory
from app.models.typeform_intake import TypeformFormConfig, TypeformIntake
from app.models.user import User
from app.services.email_branding import render_branded_email
from app.services.email_delivery import send_email
from app.services.messaging_templates import resolve_frontend_base_url, resolve_sender_profile


logger = logging.getLogger(__name__)

LOCAL_CONFIRMATION_NOT_REQUIRED = "NOT_REQUIRED"
LOCAL_CONFIRMATION_PENDING = "PENDING"
LOCAL_CONFIRMATION_CONFIRMED = "CONFIRMED"
DEFAULT_BAR_LE_DUC_ASSIGNEE_EMAIL = "estela.oliviero@piano-academie.com"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_token(value: object | None) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in raw if not unicodedata.combining(char)).lower().replace("_", "-")


def is_bar_le_duc(value: object | None) -> bool:
    token = _normalized_token(value)
    return "bar" in token and "duc" in token


def _assignee_email(config: TypeformFormConfig | None) -> str:
    configured = None
    if config is not None and isinstance(config.configuration_json, dict):
        configured = config.configuration_json.get("local_confirmation_professor_email")
    return str(configured or DEFAULT_BAR_LE_DUC_ASSIGNEE_EMAIL).strip().lower()


def ensure_local_confirmation_assignment(
    db: Session,
    *,
    intake: TypeformIntake,
    config: TypeformFormConfig | None,
) -> Professor | None:
    location = intake.detected_location or (config.location_code if config is not None else None)
    if not is_bar_le_duc(location):
        return None

    professor = db.scalar(
        select(Professor)
        .where(func.lower(Professor.email) == _assignee_email(config), Professor.active.is_(True))
        .limit(1)
    )
    if professor is None:
        logger.warning("No active professor found for Bar-le-Duc intake %s", intake.id)
        return None

    intake.local_confirmation_assignee_professor_id = professor.id
    intake.local_confirmation_assignee_name = f"{professor.first_name} {professor.last_name}".strip() or professor.email
    if intake.local_confirmation_status in {None, LOCAL_CONFIRMATION_NOT_REQUIRED}:
        intake.local_confirmation_status = LOCAL_CONFIRMATION_PENDING
        intake.local_confirmation_requested_at = intake.local_confirmation_requested_at or _utcnow()
    db.add(intake)
    return professor


def notify_local_confirmation_assignee(
    db: Session,
    *,
    intake: TypeformIntake,
    professor: Professor,
) -> bool:
    if intake.local_confirmation_status != LOCAL_CONFIRMATION_PENDING or intake.local_confirmation_notified_at is not None:
        return False

    normalized = intake.normalized_payload_json if isinstance(intake.normalized_payload_json, dict) else {}
    child_name = " ".join(
        part.strip()
        for part in (
            str(normalized.get("child_first_name") or ""),
            str(normalized.get("child_last_name") or ""),
        )
        if part.strip()
    )
    parent_name = " ".join(
        part.strip()
        for part in (
            str(normalized.get("parent_first_name") or ""),
            str(normalized.get("parent_last_name") or ""),
        )
        if part.strip()
    )
    person = child_name or parent_name or "un nouvel élève"
    task_url = f"{resolve_frontend_base_url(db).rstrip('/')}/prof/intakes/{intake.id}"
    body = render_branded_email(
        preview=f"Un nouvel intake Bar-le-Duc est arrivé pour {person}.",
        eyebrow="ACTION REQUISE",
        title="Nouvel intake Bar-le-Duc",
        greeting=f"Bonjour {professor.first_name},",
        intro="Merci de confirmer le créneau de cours et la partition à prévoir.",
        rows=[("Élève", person), ("Statut", "À confirmer")],
        message="Cette demande restera affichée dans votre espace professeur jusqu’à sa confirmation.",
        button_url=task_url,
        button_label="Ouvrir la demande",
    )
    sender = resolve_sender_profile(db, sender_kind="STUDIO")
    recipient = db.scalar(select(User).where(func.lower(User.email) == professor.email.lower()).limit(1))
    message_id = send_email(
        to_email=professor.email,
        subject=f"Action requise – intake Bar-le-Duc – {person}",
        body=body,
        body_format="HTML",
        context=f"INTAKE_LOCAL_CONFIRMATION:{intake.id}",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        sender_label=sender.from_name or "Piano Académie",
        sender_category=CommunicationSenderCategory.OTHER_USER,
        professor_id=professor.id,
        recipient_user_id=recipient.id if recipient is not None else None,
    )
    if message_id is None:
        return False
    intake.local_confirmation_notified_at = _utcnow()
    db.add(intake)
    return True
