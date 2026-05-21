from __future__ import annotations

import csv
from decimal import Decimal
import html
import io
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from xhtml2pdf import pisa
from sqlalchemy import Numeric, Text, case, cast, extract, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.client_record import ClientInvoiceLine, ClientNoteEntry
from app.models.ops import CommunicationChannel as CommunicationChannelModel, CommunicationLog, LegalEntity
from app.models.payout import ProfessorSessionPayout
from app.models.quote import Prospect, Quote, QuoteLine
from app.models.reporting import GeneratedReport
from app.models.typeform_intake import TypeformFormConfig, TypeformIntake
from app.models.user import User, UserRole
from app.schemas.report import (
    AttendanceReportRow,
    CommunicationChannel,
    CommunicationFiltersOut,
    CommunicationPeriod,
    CommunicationReportPageOut,
    CommunicationProfessorFilterOut,
    CommunicationReportRow,
    CommunicationResendRequest,
    CommunicationTypeFilterOut,
    GeneratedReportCreate,
    GeneratedReportOut,
    IntakeFamilyChildSummary,
    IntakeFamilySummaryRow,
    ProfessorStatementRow,
    ReservationReportRow,
)
from app.services.communication_journal import COMMUNICATION_TYPE_LABELS, KNOWN_COMMUNICATION_TYPES, communication_type_label
from app.services.email_delivery import email_delivery_disabled_reason, send_email
from app.services.messaging_templates import resolve_sender_profile

router = APIRouter(prefix="/admin/reports")
INVOICE_RANGE_NOTE_PREFIX = "INVOICE_RANGE::"
COMMUNICATION_ARCHIVE_RETENTION_DAYS = 365
ADMIN_COMMUNICATION_TIMEZONE = ZoneInfo("Europe/Paris")
REPORT_TYPE_LABELS: dict[str, str] = {
    "intake-families": "Synthese intakes par famille",
    "quote-families": "Synthese devis par famille",
    "reservations": "Reservations",
    "attendance": "Presence eleves",
    "professor-statements": "Releves professeurs",
    "communications": "Communications",
    "payments": "Paiements clients",
    "quotes": "Devis",
    "subscriptions": "Abonnements",
    "planning-fill": "Remplissage planning",
    "check-deposits": "Depots de cheques",
    "referrals": "Parrainages",
    "teacher-payments": "Paiement des salaires",
}


def _professor_name(prof: Professor) -> str:
    return f"{prof.first_name} {prof.last_name}".strip()


def _client_name(user: User) -> str:
    value = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return value or user.email


def _service_address(user: User) -> str:
    parts = [
        (user.address_line or "").strip(),
        (user.postal_code or "").strip(),
        (user.city or "").strip(),
        (user.address_country or "").strip().upper(),
    ]
    return " ".join(part for part in parts if part).strip()


def _invoice_fields_from_note_message(message: str | None) -> tuple[str | None, str | None]:
    raw = (message or "").strip()
    if not raw:
        return None, None
    prefix_index = raw.find(INVOICE_RANGE_NOTE_PREFIX)
    if prefix_index >= 0:
        payload = raw[prefix_index + len(INVOICE_RANGE_NOTE_PREFIX) :].strip()
        if payload:
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    invoice_number = str(parsed.get("invoice_number") or "").strip() or None
                    invoice_status = str(parsed.get("invoice_status") or "").strip().upper() or None
                    return invoice_number, invoice_status
            except json.JSONDecodeError:
                pass
    # Fallback for legacy note text if JSON payload is not present.
    match = re.search(r"\bFacture\s+([A-Za-z0-9._/-]+)", raw)
    invoice_number = match.group(1).strip() if match is not None else None
    return invoice_number, None


def _ensure_date_range(from_: datetime | None, to: datetime | None) -> None:
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before 'to'",
        )


def _day_bounds(day: date, tz: ZoneInfo = ADMIN_COMMUNICATION_TIMEZONE) -> tuple[datetime, datetime]:
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _communication_period_bounds(
    period: CommunicationPeriod,
    now_utc: datetime,
) -> tuple[datetime, datetime] | None:
    today_start, today_end = _day_bounds(now_utc.astimezone(ADMIN_COMMUNICATION_TIMEZONE).date())
    if period == CommunicationPeriod.ALL:
        return None
    if period == CommunicationPeriod.TODAY:
        return today_start, today_end
    if period == CommunicationPeriod.WEEK:
        return now_utc - timedelta(days=7), now_utc
    if period == CommunicationPeriod.MONTH:
        return now_utc - timedelta(days=30), now_utc
    if period == CommunicationPeriod.SEMESTER:
        return now_utc - timedelta(days=183), now_utc
    if period == CommunicationPeriod.YEAR:
        return now_utc - timedelta(days=365), now_utc
    return today_start, today_end


def _archive_communications_older_than_one_year(db: Session, now_utc: datetime) -> None:
    archive_before = now_utc - timedelta(days=COMMUNICATION_ARCHIVE_RETENTION_DAYS)
    db.execute(
        update(CommunicationLog)
        .where(
            CommunicationLog.archived_at.is_(None),
            CommunicationLog.occurred_at < archive_before,
        )
        .values(archived_at=now_utc, updated_at=now_utc)
    )
    db.commit()


def _parse_communication_log_id(raw_value: str) -> UUID:
    raw = str(raw_value or "").strip()
    if raw.startswith("communication-log-"):
        raw = raw[len("communication-log-") :]
    try:
        return UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Identifiant de communication invalide",
        ) from exc


def _communication_row_out(row: CommunicationLog) -> CommunicationReportRow:
    return CommunicationReportRow(
        id=f"communication-log-{row.id}",
        channel=CommunicationChannel(row.channel.value),
        source=row.source,
        communication_type=row.communication_type,
        communication_type_label=communication_type_label(row.communication_type),
        sender_category=row.sender_category.value,
        sender_label=row.sender_label,
        sender_user_id=row.sender_user_id,
        professor_id=row.professor_id,
        occurred_at=row.occurred_at,
        subject=row.subject,
        recipient=row.recipient,
        recipient_user_id=row.recipient_user_id,
        delivery_status=row.delivery_status.value,
        provider_message_id=row.provider_message_id,
        provider=row.provider,
        content=row.content,
        content_format=row.content_format.value,
        error_message=row.error_message,
    )


def _text(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _json_object(value: object | None) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _json_list(value: object | None) -> list[object]:
    return value if isinstance(value, list) else []


def _bool_or_default(value: object | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = _text(value).casefold()
    if lowered in {"1", "true", "yes", "on", "oui"}:
        return True
    if lowered in {"0", "false", "no", "off", "non"}:
        return False
    return default


def _normalize_token(value: object | None) -> str:
    raw = unicodedata.normalize("NFKD", _text(value))
    ascii_text = raw.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_text.casefold())


def _display_name(first_name: object | None, last_name: object | None, fallback: str = "-") -> str:
    label = " ".join(part for part in [_text(first_name), _text(last_name)] if part).strip()
    return label or fallback


def _generated_report_out(row: GeneratedReport) -> GeneratedReportOut:
    return GeneratedReportOut(
        id=row.id,
        report_type=row.report_type,
        report_label=row.report_label,
        file_format=row.file_format,
        period_start=row.period_start,
        period_end=row.period_end,
        note=row.note,
        row_count=row.row_count,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _parse_report_date(value: object | None) -> date | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _report_period_label(start: date | None, end: date | None) -> str:
    if start and end:
        return f"{start.isoformat()} - {end.isoformat()}"
    if start:
        return f"Depuis {start.isoformat()}"
    if end:
        return f"Jusqu au {end.isoformat()}"
    return "-"


def _form_label(config: TypeformFormConfig | None) -> str | None:
    if config is None:
        return None
    config_json = _json_object(config.configuration_json)
    return _text(config_json.get("label")) or config.source_code


def _intake_family_key(normalized: dict[str, object]) -> str | None:
    email = _text(normalized.get("parent_email")).casefold()
    if email:
        return f"email:{email}"
    phone = re.sub(r"\D+", "", _text(normalized.get("parent_phone")))
    if phone:
        return f"phone:{phone}"
    parent_name = _normalize_token(
        " ".join(
            part
            for part in [
                _text(normalized.get("parent_last_name")),
                _text(normalized.get("parent_first_name")),
            ]
            if part
        )
    )
    return f"name:{parent_name}" if parent_name else None


def _format_slot_preferences(preferences: list[object], *, include_location: bool = False) -> str | None:
    labels: list[str] = []
    for item in preferences:
        if not isinstance(item, dict):
            continue
        day = _text(item.get("day"))
        time = _text(item.get("time"))
        location = _text(item.get("location"))
        parts: list[str] = []
        if day and time:
            parts.append(f"{day.capitalize()} {time}")
        elif day:
            parts.append(day.capitalize())
        elif time:
            parts.append(time)
        if include_location and location:
            parts.append(location)
        label = " | ".join(parts).strip()
        if label:
            labels.append(label)
    return ", ".join(dict.fromkeys(labels)) or None


def _format_day_time_summary(normalized: dict[str, object]) -> str | None:
    days = [_text(item) for item in _json_list(normalized.get("requested_days")) if _text(item)]
    times = [_text(item) for item in _json_list(normalized.get("requested_times")) if _text(item)]
    labels: list[str] = []
    if days and times:
        for day in days:
            for time in times:
                labels.append(f"{day.capitalize()} {time}")
    elif days:
        labels.extend(day.capitalize() for day in days)
    else:
        labels.extend(times)
    return ", ".join(dict.fromkeys(labels)) or None


def _format_intake_course_1(normalized: dict[str, object]) -> str | None:
    location = _text(normalized.get("requested_location"))
    mode = _text(normalized.get("requested_course_mode"))
    formula = _text(normalized.get("requested_formula_type"))
    slots = _format_slot_preferences(_json_list(normalized.get("requested_slot_preferences"))) or _format_day_time_summary(normalized)
    parts = [part for part in [location, slots, mode or formula] if part]
    return " | ".join(parts) or None


def _format_intake_course_2(normalized: dict[str, object]) -> str | None:
    second_course = _json_object(normalized.get("requested_second_course"))
    if not _bool_or_default(second_course.get("requested"), False):
        return None
    value = _text(second_course.get("value")) or _text(second_course.get("label")) or "2e cours"
    modality = _text(second_course.get("modality"))
    slots = _format_slot_preferences(_json_list(second_course.get("slot_preferences")), include_location=True)
    parts = [part for part in [value, modality, slots] if part]
    return " | ".join(parts) or value


def _format_intake_solfege(normalized: dict[str, object]) -> str | None:
    products = [_text(item) for item in _json_list(normalized.get("requested_products")) if _text(item)]
    has_solfege = (
        _bool_or_default(normalized.get("requested_onsite_solfege"), False)
        or _bool_or_default(normalized.get("requested_online_solfege"), False)
        or any("solfege" in _normalize_token(item) for item in products)
        or bool(_json_list(normalized.get("requested_solfege_slot_preferences")))
    )
    if not has_solfege:
        return None
    level = _text(normalized.get("estimated_solfege_level"))
    modality = _text(normalized.get("requested_solfege_modality"))
    if modality == "online":
        modality = "en ligne"
    elif modality == "onsite":
        modality = "presentiel"
    slots = _format_slot_preferences(_json_list(normalized.get("requested_solfege_slot_preferences")), include_location=True)
    parts = [part for part in [f"Niveau {level}" if level else None, modality, slots] if part]
    return " | ".join(parts) or "Oui"


def _requested_product_contains(normalized: dict[str, object], *tokens: str) -> bool:
    normalized_tokens = tuple(_normalize_token(token) for token in tokens)
    for item in _json_list(normalized.get("requested_products")):
        product = _normalize_token(item)
        if all(token in product for token in normalized_tokens):
            return True
    return False


def _format_intake_masterclass(normalized: dict[str, object]) -> str | None:
    return "Oui" if _requested_product_contains(normalized, "masterclass") else None


def _format_intake_pass_recup(normalized: dict[str, object]) -> str | None:
    if _bool_or_default(normalized.get("requested_pass_recup"), False):
        return "Oui"
    return "Oui" if _requested_product_contains(normalized, "pass", "recup") else None


def _format_money(value: object | None, currency: str | None = "EUR") -> str:
    try:
        amount = Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except Exception:
        amount = Decimal("0.00")
    return f"{amount:.2f} {(currency or 'EUR').upper()}"


def _quote_parent_contact_from_meta(meta: dict[str, object]) -> dict[str, str]:
    typeform_meta = _json_object(meta.get("typeform_intake"))
    normalized = _json_object(typeform_meta.get("normalized_payload"))
    parent_referent = _json_object(meta.get("parent_referent"))
    return {
        "name": _display_name(
            parent_referent.get("first_name") or normalized.get("parent_first_name"),
            parent_referent.get("last_name") or normalized.get("parent_last_name"),
            fallback="",
        ),
        "email": _text(parent_referent.get("email") or normalized.get("parent_email") or meta.get("recipient_email")),
        "phone": _text(parent_referent.get("phone") or normalized.get("parent_phone")),
    }


def _quote_family_key(quote: Quote, prospect: Prospect | None, parent: Prospect | None, client: User | None) -> str:
    meta = _json_object(quote.meta)
    contact = _quote_parent_contact_from_meta(meta)
    if parent is not None:
        return f"parent-prospect:{parent.id}"
    if prospect is not None and prospect.parent_prospect_id is not None:
        return f"parent-prospect:{prospect.parent_prospect_id}"
    if contact["email"]:
        return f"email:{contact['email'].casefold()}"
    if client is not None and client.email:
        return f"client-email:{client.email.casefold()}"
    if prospect is not None and prospect.email:
        return f"prospect-email:{prospect.email.casefold()}"
    return f"quote:{quote.id}"


def _quote_family_contact(
    quote: Quote,
    prospect: Prospect | None,
    parent: Prospect | None,
    client: User | None,
) -> tuple[str, str | None, str | None, str | None]:
    meta_contact = _quote_parent_contact_from_meta(_json_object(quote.meta))
    parent_name = _display_name(parent.first_name, parent.last_name, fallback="") if parent is not None else ""
    client_name = _display_name(client.first_name, client.last_name, fallback="") if client is not None else ""
    prospect_name = _display_name(prospect.first_name, prospect.last_name, fallback="") if prospect is not None else ""
    label = parent_name or meta_contact["name"] or client_name or prospect_name or "Famille sans contact"
    email = (
        (parent.email if parent is not None else None)
        or meta_contact["email"]
        or (client.email if client is not None else None)
        or (prospect.email if prospect is not None else None)
    )
    phone = (
        (parent.phone if parent is not None else None)
        or meta_contact["phone"]
        or (client.mobile_phone_1 if client is not None else None)
        or (client.phone if client is not None else None)
        or (prospect.phone if prospect is not None else None)
    )
    return label, label if label != "Famille sans contact" else None, email, phone


def _quote_student_name(quote: Quote, prospect: Prospect | None, client: User | None) -> str:
    meta = _json_object(quote.meta)
    duplicated_name = _text(meta.get("duplicated_for_child_name"))
    if duplicated_name:
        return duplicated_name
    typeform_meta = _json_object(meta.get("typeform_intake"))
    normalized = _json_object(typeform_meta.get("normalized_payload"))
    normalized_child = _display_name(
        normalized.get("child_first_name") or normalized.get("student_first_name"),
        normalized.get("child_last_name") or normalized.get("student_last_name"),
        fallback="",
    )
    if normalized_child:
        return normalized_child
    if prospect is not None:
        return _display_name(prospect.first_name, prospect.last_name, fallback=prospect.email)
    if client is not None:
        return _display_name(client.first_name, client.last_name, fallback=client.email)
    return "Eleve non renseigne"


def _quote_child_family_surname(child_name: object | None) -> str:
    raw = unicodedata.normalize("NFKD", _text(child_name))
    ascii_text = raw.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()
    parts = [part for part in normalized.split() if part]
    return parts[-1] if len(parts) >= 2 else ""


def _quote_child_family_surname_label(child_name: object | None) -> str:
    parts = [part for part in _text(child_name).split() if part]
    return parts[-1] if len(parts) >= 2 else ""


def _quote_line_summary(lines: list[QuoteLine], *, categories: set[str], max_items: int = 8) -> str | None:
    labels: list[str] = []
    for line in lines:
        category = (line.line_category or "").strip().lower()
        line_type = (line.line_type or "").strip().lower()
        if category not in categories or line_type == "subtotal":
            continue
        qty = Decimal(line.quantity or 0).quantize(Decimal("0.01"))
        amount = Decimal(line.amount_ttc or 0).quantize(Decimal("0.01"))
        title = _text(line.title) or _text(line.code) or "Ligne"
        if qty != Decimal("1.00"):
            title = f"{title} x{qty.normalize()}"
        labels.append(f"{title} ({amount:.2f})")
    if not labels:
        return None
    visible = labels[:max_items]
    if len(labels) > max_items:
        visible.append(f"+{len(labels) - max_items} ligne(s)")
    return " | ".join(visible)


def _quote_line_search_text(line: QuoteLine) -> str:
    meta = _json_object(line.meta)
    return _normalize_token(
        " ".join(
            _text(value)
            for value in [
                line.title,
                line.description,
                line.code,
                line.line_category,
                line.line_type,
                line.master_item_type,
                meta.get("typeform_automatic_line"),
                meta.get("recommendation_key"),
            ]
        )
    )


def _quote_line_schedule_keys(line: QuoteLine) -> set[str]:
    keys: set[str] = set()
    activity_id = _text(line.activity_id)
    meta = _json_object(line.meta)
    automatic_key = _text(meta.get("typeform_automatic_line"))
    recommendation_key = _text(meta.get("recommendation_key"))
    if activity_id:
        keys.add(activity_id)
    if automatic_key:
        keys.add(automatic_key)
    if recommendation_key:
        keys.add(recommendation_key)
    if activity_id and automatic_key:
        keys.add(f"{activity_id}:{automatic_key}")
    return {key for key in keys if key}


def _quote_line_strong_schedule_keys(line: QuoteLine) -> set[str]:
    activity_id = _text(line.activity_id)
    meta = _json_object(line.meta)
    automatic_key = _text(meta.get("typeform_automatic_line"))
    recommendation_key = _text(meta.get("recommendation_key"))
    keys = {key for key in [automatic_key, recommendation_key] if key}
    if activity_id and automatic_key:
        keys.add(f"{activity_id}:{automatic_key}")
    return keys


def _quote_schedule_item_keys(item: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for key in ("recommendation_key", "line_recommendation_key", "activity_id", "source_key", "typeform_automatic_line"):
        value = _text(item.get(key))
        if value:
            keys.add(value)
    activity_id = _text(item.get("activity_id"))
    source_key = _text(item.get("source_key") or item.get("typeform_automatic_line"))
    if activity_id and source_key:
        keys.add(f"{activity_id}:{source_key}")
    return keys


def _quote_schedule_items(quote: Quote) -> list[dict[str, object]]:
    snapshot = _json_object(quote.calendar_snapshot)
    items: list[dict[str, object]] = []
    for collection_key in ("blocks", "sessions"):
        for raw in _json_list(snapshot.get(collection_key)):
            item = _json_object(raw)
            if item:
                items.append(item)
    selected_slot = _json_object(quote.selected_solfege_slot) or _json_object(
        _json_object(snapshot.get("solfege")).get("selected_slot")
    )
    if selected_slot:
        slot_item = dict(selected_slot)
        slot_item.setdefault("activity_label", "Solfege")
        slot_item.setdefault("source", "selected_solfege_slot")
        slot_item.setdefault("pending_solfege_level", quote.estimated_solfege_level)
        items.append(slot_item)
    return items


def _quote_schedule_item_label(
    item: dict[str, object],
    *,
    include_level: bool = False,
    fallback_title: str | None = None,
) -> str | None:
    day = _text(item.get("weekday_label") or item.get("day") or item.get("date_label"))
    start = _text(item.get("start_time") or item.get("start") or item.get("local_start_time"))
    end = _text(item.get("end_time") or item.get("end") or item.get("local_end_time"))
    if not day:
        starts_at = _text(item.get("start_at") or item.get("start_at_local") or item.get("start_at_utc") or item.get("date"))
        day = starts_at[:10] if starts_at else ""
    time_label = f"{start}-{end}" if start and end else start or end
    location = _text(
        item.get("location_label")
        or item.get("location_name")
        or item.get("location")
        or item.get("modality_label")
        or item.get("modality")
    )
    level = _text(item.get("pending_solfege_level") or item.get("level_code") or item.get("level"))
    parts = []
    if include_level and level:
        parts.append(f"Niveau {level}")
    parts.extend(part for part in [day, time_label, location] if part)
    if parts:
        return " · ".join(parts)
    label = _text(item.get("label"))
    if label:
        return label
    return fallback_title


def _quote_schedule_item_is_kind(item: dict[str, object], token: str) -> bool:
    item_text = _normalize_token(
        " ".join(
            _text(item.get(key))
            for key in (
                "activity_label",
                "activity_name",
                "course_type_name",
                "title",
                "label",
                "activity_code",
                "activity_service_code",
            )
        )
    )
    return token in item_text


def _quote_primary_course_schedule_items(quote: Quote) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _quote_schedule_items(quote):
        if _quote_schedule_item_is_kind(item, "solfege"):
            continue
        if _quote_schedule_item_is_kind(item, "masterclass"):
            continue
        if _text(item.get("pending_solfege_level")):
            continue
        label = _quote_schedule_item_label(item)
        if label:
            items.append(item)
    return items


def _quote_schedule_label_has_slot(label: str | None) -> bool:
    if not label:
        return False
    return bool(re.search(r"\d{1,2}:\d{2}", label)) and " · " in label


def _quote_line_schedule_label(quote: Quote, line: QuoteLine | None, *, include_level: bool = False) -> str | None:
    if line is None:
        return None
    strong_line_keys = _quote_line_strong_schedule_keys(line)
    activity_id = _text(line.activity_id)
    line_text = _quote_line_search_text(line)
    fallback_title = _text(line.title or line.description or line.code) or None
    items = _quote_schedule_items(quote)
    for item in items:
        if strong_line_keys and strong_line_keys.intersection(_quote_schedule_item_keys(item)):
            return _quote_schedule_item_label(item, include_level=include_level, fallback_title=fallback_title)
    if activity_id:
        activity_matches = [item for item in items if activity_id in _quote_schedule_item_keys(item)]
        if len(activity_matches) == 1:
            return _quote_schedule_item_label(activity_matches[0], include_level=include_level, fallback_title=fallback_title)
    for item in items:
        if "solfege" in line_text and _quote_schedule_item_is_kind(item, "solfege"):
            return _quote_schedule_item_label(item, include_level=include_level, fallback_title=fallback_title)
        if "masterclass" in line_text and _quote_schedule_item_is_kind(item, "masterclass"):
            return _quote_schedule_item_label(item, include_level=include_level, fallback_title=fallback_title)
    return fallback_title


def _quote_family_child_schedule(quote: Quote, lines: list[QuoteLine]) -> dict[str, str | None]:
    service_lines: list[QuoteLine] = []
    solfege_line: QuoteLine | None = None
    masterclass_line: QuoteLine | None = None
    second_course_line: QuoteLine | None = None

    for line in lines:
        line_type = (line.line_type or "").strip().lower()
        if line_type == "subtotal":
            continue
        text = _quote_line_search_text(line)
        if "masterclass" in text:
            masterclass_line = masterclass_line or line
            continue
        if "solfege" in text:
            solfege_line = solfege_line or line
            continue
        is_service = (line.line_category or "").strip().lower() == "service" or line.activity_id is not None
        if not is_service:
            continue
        if any(token in text for token in ("second", "deuxieme", "2e", "2eme", "secondaire")):
            second_course_line = second_course_line or line
        service_lines.append(line)

    course_1_line = next((line for line in service_lines if line is not second_course_line), None)
    if second_course_line is None and len(service_lines) >= 2:
        second_course_line = service_lines[1]

    course_items = _quote_primary_course_schedule_items(quote)
    course_1 = _quote_line_schedule_label(quote, course_1_line)
    course_2 = _quote_line_schedule_label(quote, second_course_line)
    if not _quote_schedule_label_has_slot(course_1) and course_items:
        course_1 = _quote_schedule_item_label(course_items[0], fallback_title=course_1)
    if not _quote_schedule_label_has_slot(course_2) and len(course_items) >= 2:
        course_2 = _quote_schedule_item_label(course_items[1], fallback_title=course_2)

    return {
        "course_1": course_1,
        "course_2": course_2,
        "solfege": _quote_line_schedule_label(quote, solfege_line, include_level=True),
        "masterclass": _quote_line_schedule_label(quote, masterclass_line),
    }


def _quote_planning_summary(quote: Quote, max_items: int = 8) -> str | None:
    snapshot = _json_object(quote.calendar_snapshot)
    sessions = _json_list(snapshot.get("sessions"))
    labels: list[str] = []
    for raw in sessions:
        item = _json_object(raw)
        title = _text(item.get("course_type_name") or item.get("activity_name") or item.get("title"))
        location = _text(item.get("location_name") or item.get("location"))
        day = _text(item.get("day") or item.get("weekday_label"))
        start = _text(item.get("start_time") or item.get("start") or item.get("local_start_time"))
        end = _text(item.get("end_time") or item.get("end") or item.get("local_end_time"))
        if not day:
            starts_at = _text(item.get("start_at") or item.get("start_at_local") or item.get("start_at_utc"))
            day = starts_at[:10] if starts_at else ""
        time_label = f"{start}-{end}" if start and end else start or end
        parts = [part for part in [title, location, day, time_label] if part]
        if parts:
            labels.append(" · ".join(parts))
    if not labels:
        return None
    visible = list(dict.fromkeys(labels))[:max_items]
    if len(labels) > max_items:
        visible.append(f"+{len(labels) - max_items} seance(s)")
    return " | ".join(visible)


def _quote_payment_summary(quote: Quote) -> str | None:
    snapshot = _json_object(quote.payment_terms_snapshot)
    plan_label = _text(snapshot.get("payment_plan_name") or snapshot.get("plan_name") or snapshot.get("payment_method_label"))
    schedule = _json_list(snapshot.get("schedule"))
    schedule_labels: list[str] = []
    for raw in schedule[:4]:
        item = _json_object(raw)
        amount = _text(item.get("amount_ttc") or item.get("amount") or item.get("total_ttc"))
        due = _text(item.get("due_date") or item.get("label") or item.get("deposit_label"))
        if amount or due:
            schedule_labels.append(" ".join(part for part in [due, amount] if part))
    parts = [plan_label, " | ".join(schedule_labels)]
    return " ; ".join(part for part in parts if part) or None


def _merge_quote_family_groups_by_child_surname(
    grouped: dict[str, dict[str, object]],
    latest_created: dict[str, datetime],
) -> tuple[dict[str, dict[str, object]], dict[str, datetime]]:
    buckets_by_surname: dict[tuple[str, str], list[dict[str, object]]] = {}
    for family in grouped.values():
        surnames = {
            _quote_child_family_surname(_json_object(child).get("child_name"))
            for child in _json_list(family.get("children"))
        }
        surnames.discard("")
        family_label_key = _normalize_token(family.get("family_label"))
        if len(surnames) == 1 and family_label_key and family_label_key != "famillesanscontact":
            buckets_by_surname.setdefault((next(iter(surnames)), family_label_key), []).append(family)

    merged_keys: set[str] = set()
    merged_grouped: dict[str, dict[str, object]] = {}
    merged_latest: dict[str, datetime] = {}
    for (surname, _), families in buckets_by_surname.items():
        if len(families) <= 1:
            continue
        merged_children: list[object] = []
        contacts_email: list[str] = []
        contacts_phone: list[str] = []
        surname_label = ""
        quote_count = 0
        latest = datetime.min.replace(tzinfo=timezone.utc)
        for family in families:
            family_key = _text(family.get("family_key"))
            merged_keys.add(family_key)
            latest = max(latest, latest_created.get(family_key, latest))
            quote_count += int(family.get("quote_count") or 0)
            for child in _json_list(family.get("children")):
                child_obj = _json_object(child)
                surname_label = surname_label or _quote_child_family_surname_label(child_obj.get("child_name"))
                merged_children.append(child)
            for key, target in (("parent_email", contacts_email), ("parent_phone", contacts_phone)):
                value = _text(family.get(key))
                if value and value not in target:
                    target.append(value)
        merged_key = f"child-surname:{surname}"
        merged_grouped[merged_key] = {
            "family_key": merged_key,
            "family_label": f"Famille {surname_label or surname.title()}",
            "parent_name": None,
            "parent_email": " / ".join(contacts_email[:3]) if contacts_email else None,
            "parent_phone": " / ".join(contacts_phone[:3]) if contacts_phone else None,
            "quote_count": quote_count,
            "children": merged_children,
        }
        merged_latest[merged_key] = latest

    for family_key, family in grouped.items():
        if family_key in merged_keys:
            continue
        merged_grouped[family_key] = family
        merged_latest[family_key] = latest_created.get(family_key, datetime.min.replace(tzinfo=timezone.utc))
    return merged_grouped, merged_latest


def _build_quote_family_summary_rows(
    db: Session,
    *,
    q: str | None = None,
    school_year_label: str | None = None,
    received_from: date | None = None,
    received_to: date | None = None,
    status_filter: str | None = None,
    min_children: int = 2,
    limit: int = 1000,
) -> list[dict[str, object]]:
    if received_from is not None and received_to is not None and received_from > received_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'received_from' must be before 'received_to'",
        )

    stmt = (
        select(Quote, Prospect, User)
        .outerjoin(Prospect, Prospect.id == Quote.prospect_id)
        .outerjoin(User, User.id == Quote.client_id)
        .order_by(Quote.created_at.desc())
        .limit(limit)
    )
    if school_year_label:
        stmt = stmt.where(Quote.school_year_label == school_year_label)
    if received_from is not None:
        start_local, _ = _day_bounds(received_from)
        stmt = stmt.where(Quote.created_at >= start_local)
    if received_to is not None:
        _, end_local = _day_bounds(received_to)
        stmt = stmt.where(Quote.created_at < end_local)
    if status_filter:
        stmt = stmt.where(Quote.status.ilike(status_filter.strip()))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Quote.quote_number.ilike(like),
                Quote.status.ilike(like),
                Quote.school_year_label.ilike(like),
                cast(Quote.meta, Text).ilike(like),
                Prospect.first_name.ilike(like),
                Prospect.last_name.ilike(like),
                Prospect.email.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.email.ilike(like),
            )
        )

    rows = db.execute(stmt).all()
    parent_ids = {
        prospect.parent_prospect_id
        for _, prospect, _ in rows
        if prospect is not None and prospect.parent_prospect_id is not None
    }
    parents_by_id: dict[UUID, Prospect] = {}
    if parent_ids:
        parents_by_id = {
            parent.id: parent
            for parent in db.scalars(select(Prospect).where(Prospect.id.in_(list(parent_ids)))).all()
        }
    quote_ids = [quote.id for quote, _, _ in rows]
    lines_by_quote_id: dict[UUID, list[QuoteLine]] = {quote_id: [] for quote_id in quote_ids}
    if quote_ids:
        for line in db.scalars(
            select(QuoteLine)
            .where(QuoteLine.quote_id.in_(quote_ids))
            .order_by(QuoteLine.quote_id.asc(), QuoteLine.sort_order.asc(), QuoteLine.created_at.asc())
        ).all():
            lines_by_quote_id.setdefault(line.quote_id, []).append(line)

    grouped: dict[str, dict[str, object]] = {}
    latest_created: dict[str, datetime] = {}
    for quote, prospect, client in rows:
        parent = parents_by_id.get(prospect.parent_prospect_id) if prospect is not None and prospect.parent_prospect_id is not None else None
        family_key = _quote_family_key(quote, prospect, parent, client)
        family_label, parent_name, parent_email, parent_phone = _quote_family_contact(quote, prospect, parent, client)
        bucket = grouped.get(family_key)
        if bucket is None:
            bucket = {
                "family_key": family_key,
                "family_label": family_label,
                "parent_name": parent_name,
                "parent_email": parent_email,
                "parent_phone": parent_phone,
                "quote_count": 0,
                "children": [],
            }
            grouped[family_key] = bucket
            latest_created[family_key] = quote.created_at
        else:
            bucket["parent_name"] = bucket.get("parent_name") or parent_name
            bucket["parent_email"] = bucket.get("parent_email") or parent_email
            bucket["parent_phone"] = bucket.get("parent_phone") or parent_phone
            if bucket.get("family_label") == "Famille sans contact" and family_label != "Famille sans contact":
                bucket["family_label"] = family_label
            if quote.created_at > latest_created[family_key]:
                latest_created[family_key] = quote.created_at

        lines = lines_by_quote_id.get(quote.id, [])
        child_schedule = _quote_family_child_schedule(quote, lines)
        bucket["quote_count"] = int(bucket.get("quote_count") or 0) + 1
        _json_list(bucket["children"]).append(
            {
                "quote_id": str(quote.id),
                "quote_number": quote.quote_number,
                "created_at": quote.created_at.isoformat(),
                "sent_at": quote.sent_at.isoformat() if quote.sent_at else None,
                "expires_at": quote.expires_at.isoformat() if quote.expires_at else None,
                "child_name": _quote_student_name(quote, prospect, client),
                "status": quote.status,
                "total_ttc": _format_money(quote.total_ttc, quote.currency),
                "course_1": child_schedule.get("course_1"),
                "course_2": child_schedule.get("course_2"),
                "solfege": child_schedule.get("solfege"),
                "masterclass": child_schedule.get("masterclass"),
                "services": _quote_line_summary(lines, categories={"service"}),
                "products": _quote_line_summary(lines, categories={"product", "kit"}),
                "discounts": _quote_line_summary(lines, categories={"discount", "adjustment", "fee"}),
                "planning": _quote_planning_summary(quote),
                "payment": _quote_payment_summary(quote),
            }
        )

    grouped, latest_created = _merge_quote_family_groups_by_child_surname(grouped, latest_created)
    families = [
        family
        for family in grouped.values()
        if len({_text(_json_object(child).get("child_name")).casefold() for child in _json_list(family.get("children"))}) >= min_children
    ]
    for family in families:
        _json_list(family.get("children")).sort(
            key=lambda child: (
                _text(_json_object(child).get("child_name")).casefold(),
                _text(_json_object(child).get("quote_number")),
            )
        )
    families.sort(
        key=lambda family: (
            -len(_json_list(family.get("children"))),
            _text(family.get("family_label")).casefold(),
            latest_created.get(_text(family.get("family_key")), datetime.min.replace(tzinfo=timezone.utc)),
        )
    )
    return families


@router.post("/communications/{communication_id}/resend", response_model=CommunicationReportRow)
def resend_communication(
    communication_id: str = Path(...),
    payload: CommunicationResendRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationReportRow:
    normalized_communication_id = _parse_communication_log_id(communication_id)
    row = db.scalar(select(CommunicationLog).where(CommunicationLog.id == normalized_communication_id).limit(1))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Communication introuvable")
    if row.channel != CommunicationChannelModel.EMAIL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seules les communications email peuvent etre renvoyees")

    delivery_error = email_delivery_disabled_reason()
    if delivery_error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=delivery_error)

    recipient = str((payload.recipient_email if payload is not None else None) or row.recipient or "").strip().lower()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Destinataire email introuvable")
    sender_category = getattr(row.sender_category, "value", str(row.sender_category or "")).strip().upper()
    sender = resolve_sender_profile(db, sender_kind="TEACHER" if sender_category == "PROFESSOR" else "STUDIO")

    message_id = send_email(
        to_email=recipient,
        subject=row.subject,
        body=row.content,
        body_format=row.content_format.value if hasattr(row.content_format, "value") else str(row.content_format),
        context=f"{row.source}_RESEND",
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to=sender.reply_to,
        subject_prefix=sender.subject_prefix,
        sender_user_id=row.sender_user_id,
        sender_label=row.sender_label,
        sender_category=row.sender_category,
        professor_id=row.professor_id,
        recipient_user_id=row.recipient_user_id if recipient == str(row.recipient or "").strip().lower() else None,
        communication_type=row.communication_type,
    )
    resent_row = db.scalar(
        select(CommunicationLog)
        .where(
            CommunicationLog.provider_message_id == message_id,
            CommunicationLog.channel == CommunicationChannelModel.EMAIL,
        )
        .order_by(CommunicationLog.occurred_at.desc())
        .limit(1)
    )
    if resent_row is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Renvoi journalise introuvable")
    return _communication_row_out(resent_row)


@router.get("/reservations", response_model=list[ReservationReportRow])
def report_reservations(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    professor_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ReservationReportRow]:
    _ensure_date_range(from_, to)

    stmt = (
        select(CourseSession, CourseType, Location, Professor, Booking, User)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(User, User.id == Booking.user_id)
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())).all()

    return [
        ReservationReportRow(
            session_id=session.id,
            start_at_utc=session.start_at_utc,
            end_at_utc=session.end_at_utc,
            session_status=session.status,
            course_type_id=course_type.id,
            course_type_code=course_type.code,
            course_type_name=course_type.name,
            location_id=location.id,
            location_name=location.name,
            professor_id=professor.id,
            professor_name=_professor_name(professor),
            booking_id=booking.id,
            client_email=user.email,
            booking_status=booking.status,
            total_incl_vat_snapshot=booking.total_incl_vat_snapshot,
            currency_snapshot=booking.currency_snapshot,
        )
        for session, course_type, location, professor, booking, user in rows
    ]


@router.get("/attendance", response_model=list[AttendanceReportRow])
def report_attendance(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    course_type_id: UUID | None = None,
    location_id: UUID | None = None,
    professor_id: UUID | None = None,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[AttendanceReportRow]:
    _ensure_date_range(from_, to)

    stmt = (
        select(CourseSession, CourseType, Location, Professor, Booking, User)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(Booking, Booking.session_id == CourseSession.id)
        .join(User, User.id == Booking.user_id)
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if course_type_id is not None:
        stmt = stmt.where(CourseSession.course_type_id == course_type_id)
    if location_id is not None:
        stmt = stmt.where(CourseSession.location_id == location_id)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    stmt = stmt.where(Booking.status != BookingStatus.WAITLISTED)
    if not include_cancelled:
        stmt = stmt.where(Booking.status != BookingStatus.CANCELLED)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc(), Booking.booked_at.desc())).all()

    return [
        AttendanceReportRow(
            session_id=session.id,
            start_at_utc=session.start_at_utc,
            course_type_name=course_type.name,
            location_name=location.name,
            professor_name=_professor_name(professor),
            booking_id=booking.id,
            client_email=user.email,
            attendance_status=booking.status.value,
        )
        for session, course_type, location, professor, booking, user in rows
    ]


@router.get("/professor-statements", response_model=list[ProfessorStatementRow])
def report_professor_statements(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    professor_id: UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[ProfessorStatementRow]:
    _ensure_date_range(from_, to)

    duration_hours_expr = cast(
        extract("epoch", CourseSession.end_at_utc - CourseSession.start_at_utc) / 3600.0,
        Numeric(10, 2),
    )

    booked_case = case(
        (
            Booking.status.in_(
                [
                    BookingStatus.BOOKED,
                    BookingStatus.ATTENDED,
                    BookingStatus.NO_SHOW,
                    BookingStatus.EXCUSED_ABSENCE,
                ]
            ),
            1,
        ),
        else_=0,
    )
    attended_case = case((Booking.status == BookingStatus.ATTENDED, 1), else_=0)
    no_show_case = case((Booking.status == BookingStatus.NO_SHOW, 1), else_=0)
    excused_case = case((Booking.status == BookingStatus.EXCUSED_ABSENCE, 1), else_=0)

    stmt = (
        select(
            CourseSession.id.label("session_id"),
            Professor.id.label("professor_id"),
            Professor.first_name.label("prof_first_name"),
            Professor.last_name.label("prof_last_name"),
            CourseSession.start_at_utc,
            CourseSession.end_at_utc,
            CourseSession.status,
            CourseType.name.label("course_type_name"),
            Location.name.label("location_name"),
            duration_hours_expr.label("duration_hours"),
            func.coalesce(func.sum(booked_case), 0).label("booked_students"),
            func.coalesce(func.sum(attended_case), 0).label("attended_students"),
            func.coalesce(func.sum(no_show_case), 0).label("no_show_students"),
            func.coalesce(func.sum(excused_case), 0).label("excused_absence_students"),
            ProfessorSessionPayout.hourly_rate_snapshot.label("hourly_rate_snapshot"),
            ProfessorSessionPayout.amount_snapshot.label("amount_snapshot"),
            ProfessorSessionPayout.currency_snapshot.label("currency_snapshot"),
            ProfessorSessionPayout.payout_status.label("payout_status"),
        )
        .join(Professor, Professor.id == CourseSession.professor_id)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(Location, Location.id == CourseSession.location_id)
        .outerjoin(Booking, Booking.session_id == CourseSession.id)
        .outerjoin(ProfessorSessionPayout, ProfessorSessionPayout.session_id == CourseSession.id)
        .where(CourseSession.status != SessionStatus.CANCELLED)
        .group_by(
            CourseSession.id,
            Professor.id,
            Professor.first_name,
            Professor.last_name,
            CourseSession.start_at_utc,
            CourseSession.end_at_utc,
            CourseSession.status,
            CourseType.name,
            Location.name,
            duration_hours_expr,
            ProfessorSessionPayout.hourly_rate_snapshot,
            ProfessorSessionPayout.amount_snapshot,
            ProfessorSessionPayout.currency_snapshot,
            ProfessorSessionPayout.payout_status,
        )
    )

    if from_ is not None:
        stmt = stmt.where(CourseSession.start_at_utc >= from_)
    if to is not None:
        stmt = stmt.where(CourseSession.start_at_utc <= to)
    if professor_id is not None:
        stmt = stmt.where(CourseSession.professor_id == professor_id)

    rows = db.execute(stmt.order_by(CourseSession.start_at_utc.desc())).all()

    result: list[ProfessorStatementRow] = []
    for row in rows:
        result.append(
            ProfessorStatementRow(
                session_id=row.session_id,
                professor_id=row.professor_id,
                professor_name=f"{row.prof_first_name} {row.prof_last_name}".strip(),
                start_at_utc=row.start_at_utc,
                end_at_utc=row.end_at_utc,
                session_status=row.status,
                course_type_name=row.course_type_name,
                location_name=row.location_name,
                duration_hours=float(row.duration_hours or 0),
                booked_students=int(row.booked_students or 0),
                attended_students=int(row.attended_students or 0),
                no_show_students=int(row.no_show_students or 0),
                excused_absence_students=int(row.excused_absence_students or 0),
                hourly_rate_snapshot=row.hourly_rate_snapshot,
                amount_snapshot=row.amount_snapshot,
                currency_snapshot=row.currency_snapshot,
                payout_status=(row.payout_status.value if row.payout_status is not None else None),
            )
        )

    return result


def _build_intake_family_summary_rows(
    db: Session,
    *,
    q: str | None = None,
    school_year_label: str | None = None,
    received_from: date | None = None,
    received_to: date | None = None,
    segment: str | None = None,
    status_filter: str | None = None,
    min_children: int = 2,
    limit: int = 1000,
) -> list[IntakeFamilySummaryRow]:
    if received_from is not None and received_to is not None and received_from > received_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'received_from' must be before 'received_to'",
        )
    stmt = (
        select(TypeformIntake, TypeformFormConfig)
        .outerjoin(TypeformFormConfig, TypeformFormConfig.id == TypeformIntake.form_config_id)
        .order_by(TypeformIntake.received_at.desc(), TypeformIntake.created_at.desc())
        .limit(limit)
    )
    if school_year_label:
        stmt = stmt.where(TypeformIntake.detected_school_year == school_year_label)
    if received_from is not None:
        start_local, _ = _day_bounds(received_from)
        stmt = stmt.where(TypeformIntake.received_at >= start_local)
    if received_to is not None:
        _, end_local = _day_bounds(received_to)
        stmt = stmt.where(TypeformIntake.received_at < end_local)
    if segment:
        stmt = stmt.where(TypeformIntake.detected_segment.ilike(segment.strip()))
    if status_filter:
        stmt = stmt.where(TypeformIntake.intake_status.ilike(status_filter.strip()))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                TypeformIntake.source_form_id.ilike(like),
                TypeformIntake.source_response_id.ilike(like),
                TypeformIntake.detected_location.ilike(like),
                TypeformIntake.detected_segment.ilike(like),
                cast(TypeformIntake.normalized_payload_json, Text).ilike(like),
                cast(TypeformIntake.simplified_response_json, Text).ilike(like),
            )
        )

    grouped: dict[str, IntakeFamilySummaryRow] = {}
    latest_received: dict[str, datetime] = {}
    for intake, config in db.execute(stmt).all():
        normalized = _json_object(intake.normalized_payload_json)
        customer_type = _text(normalized.get("customer_type")).casefold()
        child_name = _display_name(
            normalized.get("child_first_name"),
            normalized.get("child_last_name"),
            fallback="",
        )
        if customer_type == "adult" and not child_name:
            continue
        if not child_name:
            child_name = _display_name(
                normalized.get("student_first_name"),
                normalized.get("student_last_name"),
                fallback="Enfant sans nom",
            )
        family_key = _intake_family_key(normalized)
        if not family_key:
            family_key = f"intake:{intake.id}"

        parent_name = _display_name(
            normalized.get("parent_first_name"),
            normalized.get("parent_last_name"),
            fallback="",
        ) or None
        parent_email = _text(normalized.get("parent_email")) or None
        parent_phone = _text(normalized.get("parent_phone")) or None
        family_label = parent_name or parent_email or parent_phone or "Famille sans contact"
        bucket = grouped.get(family_key)
        if bucket is None:
            bucket = IntakeFamilySummaryRow(
                family_key=family_key,
                family_label=family_label,
                parent_name=parent_name,
                parent_email=parent_email,
                parent_phone=parent_phone,
                intake_count=0,
                children=[],
            )
            grouped[family_key] = bucket
            latest_received[family_key] = intake.received_at
        else:
            bucket.parent_name = bucket.parent_name or parent_name
            bucket.parent_email = bucket.parent_email or parent_email
            bucket.parent_phone = bucket.parent_phone or parent_phone
            if bucket.family_label == "Famille sans contact" and family_label != "Famille sans contact":
                bucket.family_label = family_label
            if intake.received_at > latest_received[family_key]:
                latest_received[family_key] = intake.received_at

        bucket.intake_count += 1
        bucket.children.append(
            IntakeFamilyChildSummary(
                intake_id=intake.id,
                received_at=intake.received_at,
                source_form_id=intake.source_form_id,
                source_form_label=_form_label(config),
                child_name=child_name,
                segment=intake.detected_segment,
                status=intake.intake_status,
                course_1=_format_intake_course_1(normalized),
                course_2=_format_intake_course_2(normalized),
                solfege=_format_intake_solfege(normalized),
                masterclass=_format_intake_masterclass(normalized),
                pass_recup=_format_intake_pass_recup(normalized),
            )
        )

    families = [
        family
        for family in grouped.values()
        if len({child.child_name.casefold() for child in family.children}) >= min_children
    ]
    for family in families:
        family.children.sort(key=lambda child: (child.child_name.casefold(), child.received_at))
    families.sort(
        key=lambda family: (
            -len(family.children),
            family.family_label.casefold(),
            latest_received.get(family.family_key, datetime.min.replace(tzinfo=timezone.utc)),
        )
    )
    return families


@router.get("/intake-families", response_model=list[IntakeFamilySummaryRow])
def report_intake_families(
    q: str | None = None,
    school_year_label: str | None = None,
    received_from: date | None = None,
    received_to: date | None = None,
    segment: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    min_children: int = Query(default=2, ge=1, le=20),
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[IntakeFamilySummaryRow]:
    return _build_intake_family_summary_rows(
        db,
        q=q,
        school_year_label=school_year_label,
        received_from=received_from,
        received_to=received_to,
        segment=segment,
        status_filter=status_filter,
        min_children=min_children,
        limit=limit,
    )


def _generated_report_html(row: GeneratedReport) -> str:
    content = _json_object(row.content_json)
    families = _json_list(content.get("families"))
    criteria = _json_object(row.criteria_json)
    title = html.escape(row.report_label)
    generated_at = row.created_at.astimezone(ADMIN_COMMUNICATION_TIMEZONE).strftime("%d/%m/%Y %H:%M")
    period_label = html.escape(_report_period_label(row.period_start, row.period_end))
    note = html.escape(row.note or "-")
    criteria_parts = [
        f"{html.escape(str(key))}: {html.escape(str(value))}"
        for key, value in criteria.items()
        if value not in (None, "", [])
    ]
    criteria_html = " | ".join(criteria_parts) or "-"
    blocks: list[str] = []
    report_rows = [
        ("course_1", "Cours 1"),
        ("course_2", "Cours 2"),
        ("solfege", "Solfege"),
        ("masterclass", "MasterClass"),
    ] if row.report_type == "quote-families" else [
        ("course_1", "Cours 1"),
        ("course_2", "Cours 2"),
        ("solfege", "Solfege"),
        ("masterclass", "Masterclass"),
        ("pass_recup", "Pass recup"),
    ]
    for family_raw in families:
        family = _json_object(family_raw)
        children = _json_list(family.get("children"))
        header_cells: list[str] = []
        for child in children:
            child_obj = _json_object(child)
            child_name = html.escape(_text(child_obj.get("child_name")) or "-")
            if row.report_type == "quote-families":
                quote_bits = [
                    _text(child_obj.get("quote_number")),
                    _text(child_obj.get("status")),
                    _text(child_obj.get("total_ttc")),
                ]
                meta = " · ".join(bit for bit in quote_bits if bit)
                header_cells.append(f"<th>{child_name}<br><span class='small'>{html.escape(meta)}</span></th>")
            else:
                header_cells.append(f"<th>{child_name}</th>")
        headers = "".join(header_cells)
        rows: list[str] = []
        for key, label in report_rows:
            cells = "".join(
                f"<td>{html.escape(_text(_json_object(child).get(key)) or '-')}</td>"
                for child in children
            )
            rows.append(f"<tr><th>{label}</th>{cells}</tr>")
        contact = _text(family.get("parent_email")) or _text(family.get("parent_phone")) or "-"
        count_label = f"{len(children)} devis" if row.report_type == "quote-families" else f"{len(children)} demande(s)"
        blocks.append(
            "<section class='family'>"
            f"<h2>{html.escape(_text(family.get('family_label')) or 'Famille')}</h2>"
            f"<p>{html.escape(count_label)} | {html.escape(contact)}</p>"
            "<table><thead><tr><th>Element</th>"
            f"{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
            "</section>"
        )
    if not blocks:
        blocks.append("<p>Aucune donnee pour ce rapport.</p>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "@page { size: A4 landscape; margin: 18mm; }"
        "body { font-family: Arial, sans-serif; color: #222; font-size: 10pt; }"
        "h1 { font-size: 20pt; margin: 0 0 8px; } h2 { font-size: 13pt; margin: 18px 0 4px; }"
        ".meta { color: #555; margin-bottom: 14px; }"
        "table { width: 100%; border-collapse: collapse; margin-top: 8px; }"
        "th, td { border: 1px solid #ccd3dd; padding: 6px; vertical-align: top; }"
        "th { background: #eef2f6; text-align: left; } .family { page-break-inside: avoid; }"
        ".small { color: #596579; font-size: 8pt; font-weight: normal; }"
        "</style></head><body>"
        f"<h1>{title}</h1>"
        f"<p class='meta'>Genere le {generated_at} | Periode: {period_label} | Format: PDF | Note: {note}</p>"
        f"<p class='meta'>Criteres: {criteria_html}</p>"
        f"{''.join(blocks)}"
        "</body></html>"
    )


def _render_generated_report_pdf(row: GeneratedReport) -> bytes:
    output = io.BytesIO()
    result = pisa.CreatePDF(src=_generated_report_html(row), dest=output, encoding="utf-8")
    if result.err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Generation PDF impossible")
    return output.getvalue()


@router.get("/generated", response_model=list[GeneratedReportOut])
def list_generated_reports(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[GeneratedReportOut]:
    rows = db.scalars(select(GeneratedReport).order_by(GeneratedReport.created_at.desc()).limit(500)).all()
    return [_generated_report_out(row) for row in rows]


@router.post("/generated", response_model=GeneratedReportOut, status_code=status.HTTP_201_CREATED)
def create_generated_report(
    payload: GeneratedReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> GeneratedReportOut:
    report_type = payload.report_type.strip()
    report_label = REPORT_TYPE_LABELS.get(report_type, report_type)
    criteria = dict(payload.criteria or {})
    period_start = payload.period_start or _parse_report_date(criteria.get("received_from"))
    period_end = payload.period_end or _parse_report_date(criteria.get("received_to"))
    if period_start is not None and period_end is not None and period_start > period_end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'period_start' must be before 'period_end'")

    content: dict[str, object] = {"items": []}
    row_count = 0
    if report_type == "intake-families":
        try:
            min_children = int(criteria.get("min_children") or 2)
        except (TypeError, ValueError):
            min_children = 2
        min_children = max(1, min(20, min_children))
        families = _build_intake_family_summary_rows(
            db,
            q=_text(criteria.get("q")) or None,
            school_year_label=_text(criteria.get("school_year_label")) or None,
            received_from=period_start,
            received_to=period_end,
            segment=_text(criteria.get("segment")) or None,
            status_filter=_text(criteria.get("status")) or None,
            min_children=min_children,
            limit=5000,
        )
        content = {"families": [family.model_dump(mode="json") for family in families]}
        row_count = len(families)
    elif report_type == "quote-families":
        try:
            min_children = int(criteria.get("min_children") or 2)
        except (TypeError, ValueError):
            min_children = 2
        min_children = max(1, min(20, min_children))
        families = _build_quote_family_summary_rows(
            db,
            q=_text(criteria.get("q")) or None,
            school_year_label=_text(criteria.get("school_year_label")) or None,
            received_from=period_start,
            received_to=period_end,
            status_filter=_text(criteria.get("status")) or None,
            min_children=min_children,
            limit=5000,
        )
        content = {"families": families}
        row_count = len(families)

    row = GeneratedReport(
        report_type=report_type,
        report_label=report_label,
        file_format="PDF",
        period_start=period_start,
        period_end=period_end,
        note=_text(payload.note) or None,
        criteria_json=criteria,
        content_json=content,
        row_count=row_count,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _generated_report_out(row)


@router.get("/generated/{report_id}/pdf")
def download_generated_report_pdf(
    report_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    row = db.get(GeneratedReport, report_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable")
    filename = f"rapport-{row.report_type}-{row.created_at.strftime('%Y%m%d')}.pdf".replace('"', "")
    return Response(
        content=_render_generated_report_pdf(row),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/generated/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated_report(
    report_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    row = db.get(GeneratedReport, report_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapport introuvable")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sap/{year}/csv")
def report_sap_csv(
    year: int = Path(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> Response:
    services_entity_id = db.scalar(
        select(LegalEntity.id).where(func.upper(func.trim(LegalEntity.name)) == "PIANO ACADEMIE SERVICES").limit(1)
    )
    if services_entity_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Legal entity 'PIANO ACADEMIE SERVICES' not found",
        )

    period_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    rows = db.execute(
        select(ClientInvoiceLine, ClientNoteEntry, User)
        .join(ClientNoteEntry, ClientNoteEntry.id == ClientInvoiceLine.note_id)
        .join(User, User.id == ClientInvoiceLine.user_id)
        .where(
            ClientInvoiceLine.seller_legal_entity_id == services_entity_id,
            ClientInvoiceLine.occurred_at >= period_start,
            ClientInvoiceLine.occurred_at < period_end,
        )
        .order_by(
            func.lower(func.coalesce(User.last_name, "")),
            func.lower(func.coalesce(User.first_name, "")),
            func.lower(User.email),
            ClientInvoiceLine.occurred_at.asc(),
            ClientInvoiceLine.id.asc(),
        )
    ).all()

    grouped: dict[str, dict[str, object]] = {}
    for line, note, client in rows:
        client_id = str(client.id)
        bucket = grouped.setdefault(
            client_id,
            {
                "client_id": client_id,
                "client_name": _client_name(client),
                "client_email": client.email,
                "service_address": _service_address(client),
                "total_paid_ttc": Decimal("0.00"),
                "details": [],
            },
        )
        invoice_number, payment_status = _invoice_fields_from_note_message(note.message)
        line_total = Decimal(line.total_incl_vat or 0).quantize(Decimal("0.01"))
        bucket["total_paid_ttc"] = (Decimal(bucket["total_paid_ttc"]) + line_total).quantize(Decimal("0.01"))
        details_bucket = bucket["details"]
        if not isinstance(details_bucket, list):
            details_bucket = []
            bucket["details"] = details_bucket
        details_bucket.append(
            {
                "line_occurred_at": line.occurred_at,
                "invoice_number": invoice_number or "",
                "label": line.label or "",
                "total_incl_vat": line_total,
                "currency": (line.currency or "").upper(),
                "note_id": str(line.note_id),
                "payment_status": payment_status or "",
            }
        )

    output_rows: list[dict[str, str]] = []
    sorted_clients = sorted(
        grouped.values(),
        key=lambda row: (
            str(row["client_name"]).casefold(),
            str(row["client_email"]).casefold(),
        ),
    )
    for bucket in sorted_clients:
        details_raw = bucket.get("details")
        details = details_raw if isinstance(details_raw, list) else []
        details.sort(
            key=lambda row: (
                row.get("line_occurred_at")
                if isinstance(row, dict) and isinstance(row.get("line_occurred_at"), datetime)
                else period_start
            )
        )
        statuses = sorted({str(row["payment_status"]).strip().upper() for row in details if str(row["payment_status"]).strip()})
        summary_status = statuses[0] if len(statuses) == 1 else ("MIXED" if statuses else "")
        total_paid = Decimal(bucket["total_paid_ttc"]).quantize(Decimal("0.01"))

        output_rows.append(
            {
                "row_type": "SUMMARY",
                "year": str(year),
                "client_id": str(bucket["client_id"]),
                "client_name": str(bucket["client_name"]),
                "client_email": str(bucket["client_email"]),
                "total_paid_ttc": f"{total_paid:.2f}",
                "line_occurred_at": "",
                "invoice_number": "",
                "label": "TOTAL_CLIENT",
                "total_incl_vat": "",
                "currency": "",
                "service_address": str(bucket["service_address"]),
                "note_id": "",
                "payment_status": summary_status,
            }
        )
        for detail in details:
            detail_occurred_at = detail.get("line_occurred_at")
            detail_total = detail.get("total_incl_vat")
            try:
                detail_total_decimal = Decimal(str(detail_total)).quantize(Decimal("0.01"))
            except Exception:
                detail_total_decimal = Decimal("0.00")
            output_rows.append(
                {
                    "row_type": "DETAIL",
                    "year": str(year),
                    "client_id": str(bucket["client_id"]),
                    "client_name": str(bucket["client_name"]),
                    "client_email": str(bucket["client_email"]),
                    "total_paid_ttc": f"{total_paid:.2f}",
                    "line_occurred_at": (detail_occurred_at.isoformat() if isinstance(detail_occurred_at, datetime) else ""),
                    "invoice_number": str(detail["invoice_number"]),
                    "label": str(detail["label"]),
                    "total_incl_vat": f"{detail_total_decimal:.2f}",
                    "currency": str(detail["currency"]),
                    "service_address": str(bucket["service_address"]),
                    "note_id": str(detail["note_id"]),
                    "payment_status": str(detail["payment_status"]),
                }
            )

    csv_columns = [
        "row_type",
        "year",
        "client_id",
        "client_name",
        "client_email",
        "total_paid_ttc",
        "line_occurred_at",
        "invoice_number",
        "label",
        "total_incl_vat",
        "currency",
        "service_address",
        "note_id",
        "payment_status",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=csv_columns)
    writer.writeheader()
    writer.writerows(output_rows)

    file_name = f"sap_services_export_{year}.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/communications", response_model=CommunicationReportPageOut)
def report_communications(
    channel: CommunicationChannel | None = Query(default=None),
    period: CommunicationPeriod = Query(default=CommunicationPeriod.TODAY),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=25, le=100),
    q: str | None = Query(default=None),
    communication_type: str | None = Query(default=None),
    occurred_on: date | None = Query(default=None),
    professor_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationReportPageOut:
    if per_page not in (25, 50, 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="per_page must be one of: 25, 50, 100",
        )

    now_utc = datetime.now(timezone.utc)
    _archive_communications_older_than_one_year(db, now_utc)

    normalized_type = (communication_type or "").strip().upper()
    search = (q or "").strip()
    period_bounds = _communication_period_bounds(period, now_utc)
    if occurred_on is not None:
        period_bounds = _day_bounds(occurred_on)

    filters: list = []
    if channel is not None:
        filters.append(CommunicationLog.channel == channel.value)
    if period_bounds is not None:
        start_at, end_at = period_bounds
        filters.append(CommunicationLog.occurred_at >= start_at)
        filters.append(CommunicationLog.occurred_at < end_at)

    if normalized_type and normalized_type != "ALL":
        filters.append(func.upper(CommunicationLog.communication_type) == normalized_type)
    if professor_id is not None:
        filters.append(CommunicationLog.professor_id == professor_id)
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(CommunicationLog.subject).like(pattern),
                func.lower(CommunicationLog.sender_label).like(pattern),
                func.lower(CommunicationLog.recipient).like(pattern),
                func.lower(CommunicationLog.content).like(pattern),
                func.lower(CommunicationLog.source).like(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(CommunicationLog)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int(db.scalar(count_stmt) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = min(page, total_pages)
    offset = (current_page - 1) * per_page

    data_stmt = select(CommunicationLog)
    if filters:
        data_stmt = data_stmt.where(*filters)
    data_stmt = data_stmt.order_by(CommunicationLog.occurred_at.desc()).offset(offset).limit(per_page)
    rows = db.scalars(data_stmt).all()

    return CommunicationReportPageOut(
        items=[_communication_row_out(row) for row in rows],
        page=current_page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


@router.get("/communications/filters", response_model=CommunicationFiltersOut)
def report_communication_filters(
    channel: CommunicationChannel | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
) -> CommunicationFiltersOut:
    type_codes: set[str] = set()
    for code in KNOWN_COMMUNICATION_TYPES:
        type_codes.add(code)
    db_type_stmt = select(CommunicationLog.communication_type).distinct()
    if channel is not None:
        db_type_stmt = db_type_stmt.where(CommunicationLog.channel == channel.value)
    db_type_rows = db.scalars(db_type_stmt).all()
    for code in db_type_rows:
        normalized = (code or "").strip().upper()
        if normalized:
            type_codes.add(normalized)
    communication_types = [
        CommunicationTypeFilterOut(code=code, label=communication_type_label(code))
        for code in sorted(type_codes, key=lambda item: COMMUNICATION_TYPE_LABELS.get(item, item))
    ]

    professors = db.scalars(
        select(Professor)
        .where(Professor.active.is_(True))
        .order_by(Professor.first_name.asc(), Professor.last_name.asc())
    ).all()
    professor_options = [
        CommunicationProfessorFilterOut(
            id=professor.id,
            label=f"{(professor.first_name or '').strip()} {(professor.last_name or '').strip()}".strip() or professor.email,
        )
        for professor in professors
    ]

    return CommunicationFiltersOut(
        communication_types=communication_types,
        professors=professor_options,
    )
