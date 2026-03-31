from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.services.messaging_templates import (
    render_template_content,
    resolve_frontend_base_url,
    resolve_predefined_template,
)

PREDEFINED_EMAIL_TEMPLATE_CLIENT_BOOKING_CONFIRMATION = "CLIENT_BOOKING_CONFIRMATION"
PREDEFINED_EMAIL_TEMPLATE_ADMIN_BOOKING_CONFIRMATION = "ADMIN_BOOKING_CONFIRMATION"


@dataclass(frozen=True)
class RenderedBookingConfirmationEmail:
    subject: str
    body: str
    body_format: str


def _render_template(template: str, context: dict[str, str]) -> str:
    return render_template_content(template, context)


def _frontend_url(path: str) -> str:
    base = resolve_frontend_base_url()
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "https://" + base
    return base.rstrip("/") + path


def _localized_start_at(start_at: datetime, timezone_name: str | None) -> datetime:
    candidate = (timezone_name or "").strip() or "Europe/Paris"
    try:
        tz = ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("Europe/Paris")
    return start_at.astimezone(tz)


def _default_rendered_email(
    *,
    audience: Literal["CLIENT", "ADMIN"],
    context: dict[str, str],
) -> RenderedBookingConfirmationEmail:
    teacher_name = context.get("teacher_name", "").strip()
    if audience == "ADMIN":
        subject = f"Nouvelle reservation confirmee - {context['activity_name']}"
        body = (
            "Une reservation a ete confirmee.\n\n"
            f"Eleve: {context['student_name']}\n"
            f"Activite: {context['activity_name']}\n"
            f"Date: {context['session_date']}\n"
            f"Heure: {context['session_time']}\n"
            f"Lieu: {context['location_name']}\n"
        )
        if teacher_name:
            body += f"Professeur: {teacher_name}\n"
        return RenderedBookingConfirmationEmail(subject=subject, body=body, body_format="TEXT")

    subject = f"Confirmation de votre reservation - {context['activity_name']}"
    body = (
        f"Bonjour {context['recipient_name']},\n\n"
        "Votre reservation est confirmee.\n\n"
        f"Eleve: {context['student_name']}\n"
        f"Activite: {context['activity_name']}\n"
        f"Date: {context['session_date']}\n"
        f"Heure: {context['session_time']}\n"
        f"Lieu: {context['location_name']}\n"
        f"Mon compte: {context['account_url']}\n\n"
        "Piano Academie"
    )
    if teacher_name:
        body = body.replace(
            f"Lieu: {context['location_name']}\n",
            f"Lieu: {context['location_name']}\nProfesseur: {teacher_name}\n",
            1,
        )
    return RenderedBookingConfirmationEmail(subject=subject, body=body, body_format="TEXT")


def _normalize_teacher_name(teacher_name: str | None) -> str:
    candidate = (teacher_name or "").strip()
    lowered = candidate.casefold()
    if lowered in {"", "a confirmer", "à confirmer", "sans professeur"}:
        return ""
    return candidate


def _strip_teacher_field(body: str, *, body_format: str) -> str:
    if body_format == "HTML":
        normalized = re.sub(
            r"<li>\s*<strong>\s*Professeur\s*:\s*</strong>\s*(?:A confirmer)?\s*</li>",
            "",
            body,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"<div class=\"email-summary-row\">\s*<span[^>]*>\s*Professeur\s*</span>\s*<strong[^>]*>\s*(?:A confirmer)?\s*</strong>\s*</div>",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized

    normalized = re.sub(r"^Professeur:\s*(?:A confirmer)?\s*$\n?", "", body, flags=re.IGNORECASE | re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def render_booking_confirmation_email(
    db: Session,
    *,
    audience: Literal["CLIENT", "ADMIN"],
    recipient_name: str | None,
    student_name: str,
    activity_name: str,
    start_at: datetime,
    timezone_name: str | None,
    location_name: str | None,
    teacher_name: str | None,
) -> RenderedBookingConfirmationEmail | None:
    localized_start = _localized_start_at(start_at, timezone_name)
    normalized_teacher_name = _normalize_teacher_name(teacher_name)
    context = {
        "recipient_name": (recipient_name or "").strip() or ("Administration" if audience == "ADMIN" else "Client"),
        "student_name": student_name.strip() or "-",
        "activity_name": activity_name.strip() or "-",
        "session_date": localized_start.strftime("%d/%m/%Y"),
        "session_time": localized_start.strftime("%H:%M"),
        "session_start_local": localized_start.strftime("%d/%m/%Y %H:%M"),
        "location_name": (location_name or "").strip() or "-",
        "teacher_name": normalized_teacher_name,
        "account_url": _frontend_url("/client?tab=planning"),
    }

    template_code = (
        PREDEFINED_EMAIL_TEMPLATE_CLIENT_BOOKING_CONFIRMATION
        if audience == "CLIENT"
        else PREDEFINED_EMAIL_TEMPLATE_ADMIN_BOOKING_CONFIRMATION
    )
    try:
        template = resolve_predefined_template(db, code=template_code)
    except KeyError:
        return _default_rendered_email(audience=audience, context=context)

    if not bool(template.get("active", True)):
        return None

    subject_template = str(template.get("subject") or "").strip()
    body_template = str(template.get("body") or "").strip()
    if not subject_template or not body_template:
        return _default_rendered_email(audience=audience, context=context)

    body_format = "HTML" if str(template.get("body_format") or "").strip().upper() == "HTML" else "TEXT"
    rendered = RenderedBookingConfirmationEmail(
        subject=_render_template(subject_template, context),
        body=_render_template(body_template, context),
        body_format=body_format,
    )
    if normalized_teacher_name:
        return rendered
    return RenderedBookingConfirmationEmail(
        subject=rendered.subject,
        body=_strip_teacher_field(rendered.body, body_format=body_format),
        body_format=rendered.body_format,
    )
