from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.ops import LegalEntity
from app.services.i18n import normalize_language
from app.services.payouts import resolve_hourly_rate_for_session

_MONTH_LABELS = {
    "fr": (
        "janvier",
        "fevrier",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "aout",
        "septembre",
        "octobre",
        "novembre",
        "decembre",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_bounds_utc(*, year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def session_duration_hours(session_obj: CourseSession) -> Decimal:
    seconds = Decimal((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds())
    return _quantize(seconds / Decimal(3600))


@dataclass
class ComputedStatementLine:
    course_type_id: UUID | None
    course_type_label: str
    hours: Decimal
    unit_rate_ht: Decimal
    amount_ht: Decimal
    amount_ttc: Decimal
    meta: dict[str, Any]


@dataclass
class ComputedMissingSession:
    session_id: UUID
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    pending_students_count: int
    total_students_count: int


@dataclass
class ComputedStatement:
    teacher_id: UUID
    payor_legal_entity_id: UUID
    payor_legal_entity_name: str
    year: int
    month: int
    attendance_complete: bool
    currency: str
    totals_ht: Decimal
    totals_vat: Decimal
    totals_ttc: Decimal
    lines: list[ComputedStatementLine]
    missing_sessions: list[ComputedMissingSession]


def compute_teacher_monthly_statements(
    db: Session,
    *,
    professor: Professor,
    year: int,
    month: int,
) -> list[ComputedStatement]:
    now = _utcnow()
    period_start, period_end = month_bounds_utc(year=year, month=month)
    session_rows = db.execute(
        select(CourseSession, CourseType, LegalEntity, Location)
        .join(CourseType, CourseType.id == CourseSession.course_type_id)
        .join(LegalEntity, LegalEntity.id == CourseSession.snapshot_payor_legal_entity_id)
        .join(Location, Location.id == CourseSession.location_id)
        .where(
            func.coalesce(CourseSession.substitute_teacher_id, CourseSession.professor_id) == professor.id,
            CourseSession.start_at_utc >= period_start,
            CourseSession.start_at_utc < period_end,
            CourseSession.status != SessionStatus.CANCELLED,
        )
        .order_by(CourseSession.start_at_utc.asc(), CourseSession.id.asc())
    ).all()
    if not session_rows:
        return []

    session_ids = [session_obj.id for session_obj, _, _, _ in session_rows]
    pending_count_expr = func.sum(case((Booking.status == BookingStatus.BOOKED, 1), else_=0))
    total_count_expr = func.count(Booking.id)
    booking_stats_rows = db.execute(
        select(
            Booking.session_id,
            pending_count_expr.label("pending_count"),
            total_count_expr.label("total_count"),
        )
        .where(
            Booking.session_id.in_(session_ids),
            Booking.status.in_(
                (
                    BookingStatus.BOOKED,
                    BookingStatus.ATTENDED,
                    BookingStatus.NO_SHOW,
                    BookingStatus.EXCUSED_ABSENCE,
                )
            ),
        )
        .group_by(Booking.session_id)
    ).all()
    stats_by_session: dict[UUID, tuple[int, int]] = {}
    for session_id, pending_count, total_count in booking_stats_rows:
        stats_by_session[session_id] = (int(pending_count or 0), int(total_count or 0))

    grouped_rows: dict[UUID, list[tuple[CourseSession, CourseType, LegalEntity, Location]]] = defaultdict(list)
    for row in session_rows:
        grouped_rows[row[0].snapshot_payor_legal_entity_id].append(row)

    vat_applicable = bool(professor.teacher_is_vat_applicable)
    vat_rate = _quantize(Decimal(professor.teacher_vat_rate or 0)) if vat_applicable else Decimal("0.00")
    fallback_currency = (professor.payout_currency or "EUR").strip().upper() or "EUR"
    computed: list[ComputedStatement] = []

    for payor_legal_entity_id, rows in grouped_rows.items():
        payor = rows[0][2]
        line_map: dict[tuple[UUID | None, str, Decimal], ComputedStatementLine] = {}
        missing_sessions: list[ComputedMissingSession] = []
        attendance_complete = True

        for session_obj, course_type, _, location in rows:
            pending_count, total_count = stats_by_session.get(session_obj.id, (0, 0))
            if pending_count > 0 and session_obj.start_at_utc <= now:
                attendance_complete = False
                missing_sessions.append(
                    ComputedMissingSession(
                        session_id=session_obj.id,
                        title=session_obj.title,
                        start_at_utc=session_obj.start_at_utc,
                        end_at_utc=session_obj.end_at_utc,
                        pending_students_count=pending_count,
                        total_students_count=total_count,
                    )
                )

            duration_hours = session_duration_hours(session_obj)
            resolved_rate = resolve_hourly_rate_for_session(
                db,
                session_obj=session_obj,
                on_date=session_obj.start_at_utc.date(),
                professor_id_override=professor.id,
                default_grid_lines=None,
            )
            unit_rate_ht = _quantize(Decimal(resolved_rate.hourly_rate if resolved_rate is not None else 0))
            amount_ht = _quantize(duration_hours * unit_rate_ht)
            if vat_applicable:
                amount_ttc = _quantize(amount_ht * (Decimal("1.00") + (vat_rate / Decimal("100.00"))))
            else:
                amount_ttc = amount_ht
            vat_amount = _quantize(amount_ttc - amount_ht)
            duration_minutes = max(1, int((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds() // 60))
            session_item = {
                "session_id": str(session_obj.id),
                "title": (session_obj.title or "").strip() or course_type.name,
                "date": session_obj.start_at_utc.date().isoformat(),
                "start_at_utc": session_obj.start_at_utc.isoformat(),
                "end_at_utc": session_obj.end_at_utc.isoformat(),
                "student_or_group": (session_obj.title or "").strip() or None,
                "location_name": (location.name or "").strip() or "-",
                "modality": "ONLINE" if bool(location.is_online) else "ONSITE",
                "duration_minutes": duration_minutes,
                "unit_rate_ht": f"{unit_rate_ht}",
                "amount_ht": f"{amount_ht}",
                "vat_amount": f"{vat_amount}",
                "amount_ttc": f"{amount_ttc}",
            }

            key = (course_type.id, course_type.name, unit_rate_ht)
            existing = line_map.get(key)
            if existing is None:
                line_map[key] = ComputedStatementLine(
                    course_type_id=course_type.id,
                    course_type_label=course_type.name,
                    hours=duration_hours,
                    unit_rate_ht=unit_rate_ht,
                    amount_ht=amount_ht,
                    amount_ttc=amount_ttc,
                    meta={
                        "sessions_count": 1,
                        "last_session_id": str(session_obj.id),
                        "session_items": [session_item],
                    },
                )
            else:
                existing.hours = _quantize(existing.hours + duration_hours)
                existing.amount_ht = _quantize(existing.amount_ht + amount_ht)
                existing.amount_ttc = _quantize(existing.amount_ttc + amount_ttc)
                existing.meta["sessions_count"] = int(existing.meta.get("sessions_count", 0)) + 1
                existing.meta["last_session_id"] = str(session_obj.id)
                items = existing.meta.get("session_items")
                if isinstance(items, list):
                    items.append(session_item)
                else:
                    existing.meta["session_items"] = [session_item]

        lines = sorted(line_map.values(), key=lambda row: (row.course_type_label.casefold(), str(row.course_type_id or "")))
        totals_ht = _quantize(sum((row.amount_ht for row in lines), Decimal("0.00")))
        totals_ttc = _quantize(sum((row.amount_ttc for row in lines), Decimal("0.00")))
        totals_vat = _quantize(totals_ttc - totals_ht)

        computed.append(
            ComputedStatement(
                teacher_id=professor.id,
                payor_legal_entity_id=payor_legal_entity_id,
                payor_legal_entity_name=(payor.name or "").strip() or "Entite",
                year=year,
                month=month,
                attendance_complete=attendance_complete,
                currency=fallback_currency,
                totals_ht=totals_ht,
                totals_vat=totals_vat,
                totals_ttc=totals_ttc,
                lines=lines,
                missing_sessions=missing_sessions,
            )
        )

    computed.sort(key=lambda row: row.payor_legal_entity_name.casefold())
    return computed


def statement_to_snapshot_payload(statement: ComputedStatement) -> dict[str, Any]:
    return {
        "teacher_id": str(statement.teacher_id),
        "payor_legal_entity_id": str(statement.payor_legal_entity_id),
        "payor_legal_entity_name": statement.payor_legal_entity_name,
        "year": statement.year,
        "month": statement.month,
        "attendance_complete": statement.attendance_complete,
        "currency": statement.currency,
        "totals_ht": f"{statement.totals_ht}",
        "totals_vat": f"{statement.totals_vat}",
        "totals_ttc": f"{statement.totals_ttc}",
        "lines": [
            {
                "course_type_id": str(line.course_type_id) if line.course_type_id is not None else None,
                "course_type_label": line.course_type_label,
                "hours": f"{line.hours}",
                "unit_rate_ht": f"{line.unit_rate_ht}",
                "amount_ht": f"{line.amount_ht}",
                "amount_ttc": f"{line.amount_ttc}",
                "meta": line.meta,
            }
            for line in statement.lines
        ],
        "missing_sessions": [
            {
                "session_id": str(row.session_id),
                "title": row.title,
                "start_at_utc": row.start_at_utc.isoformat(),
                "end_at_utc": row.end_at_utc.isoformat(),
                "pending_students_count": row.pending_students_count,
                "total_students_count": row.total_students_count,
            }
            for row in statement.missing_sessions
        ],
    }


def invoice_period_label(*, year: int, month: int, language: str | None = None) -> str:
    normalized_language = normalize_language(language)
    labels = _MONTH_LABELS.get(normalized_language, _MONTH_LABELS["fr"])
    return f"{labels[month - 1]} {year}"
