from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Any
import unicodedata
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import (
    Booking,
    BookingStatus,
    CourseSession,
    CourseSessionProfessor,
    CourseType,
    Location,
    SessionStatus,
)
from app.models.client_record import ClientInvoiceLine
from app.models.quote import Quote, QuoteAcceptanceFollowup, QuoteEvent
from app.models.user import User
from app.services.reminders import ensure_booking_reminder


ACTIVE_BOOKING_STATUSES = {
    BookingStatus.BOOKED,
    BookingStatus.ATTENDED,
    BookingStatus.NO_SHOW,
    BookingStatus.EXCUSED_ABSENCE,
}
EXECUTION_KEY = "quote_to_enrollment_execution"
TRANSFORMATION_KEY = "quote_to_enrollment"
CONFIRMED_VARIANCE_EVENT = "quote_planning_variance_confirmed"
PARIS_2026_2027_ANNUAL_COUNTS = {
    0: 31,
    1: 33,
    2: 32,
    3: 32,
    4: 32,
    5: 31,
}
PARIS_2026_2027_START_UTC = datetime(2026, 9, 1, tzinfo=timezone.utc)
PARIS_2026_2027_END_UTC = datetime(2027, 7, 1, tzinfo=timezone.utc)

# These recurrence groups were individually audited against their immutable
# accepted-quote snapshots on 2026-08-28.  Keep the general audit broad, but
# only let the automatic repair touch this reviewed batch.  This prevents a
# later, intentional planning change from being silently reverted to the
# original quote.
APPROVED_REPAIR_SERIES = {
    UUID("ac6f0f6a-1345-4d61-ac97-edffb7cc2edb"),
    UUID("c479f985-408a-4823-bc78-0ba62be5fd1c"),
    UUID("1f571738-6410-4839-b880-315c88493728"),
    UUID("a7b1d0fa-a1e9-4e1c-88cb-f0f33ec0189b"),
    UUID("5341caa3-55e2-427f-8d0e-3eb4a9175706"),
    UUID("0919d1f6-9079-4892-9a31-ddc45323dac5"),
    UUID("47d0dfed-23a3-4135-8d8b-443cd6a96bb9"),
    UUID("ce817cef-7786-4727-b40d-1414a0c2c0c2"),
    UUID("9ec47599-2867-4bd0-831f-a535f446c691"),
}


def _json_object(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _json_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _parse_date(value: object) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _zone(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "Europe/Paris")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")


def _money(value: object) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _display_name(user: User) -> str:
    name = " ".join(part for part in ((user.first_name or "").strip(), (user.last_name or "").strip()) if part)
    return name or user.email


def _normalized_label(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in raw if not unicodedata.combining(char)).lower().split())


def _paris_annual_target_count(
    *,
    school_year: str,
    course_type: CourseType,
    location: Location,
    template: CourseSession,
) -> int | None:
    """Return the reviewed Paris annual volume for piano/initiation series.

    Paris ado/adult courses intentionally follow the same school calendar as
    Paris children. Solfege, eveil and Masterclass have their own volumes and
    are deliberately excluded here.
    """

    if school_year != "2026-2027":
        return None
    location_name = _normalized_label(location.name)
    if location.is_online or "online" in location_name or "bar-le-duc" in location_name:
        return None
    activity_name = _normalized_label(course_type.name)
    if any(token in activity_name for token in ("solfege", "eveil", "masterclass")):
        return None
    if not any(
        token in activity_name
        for token in (
            "cours de piano",
            "initiation au piano",
            "cours collectifs ado/adultes",
        )
    ):
        return None
    local_start = template.start_at_utc.astimezone(_zone(template.timezone))
    return PARIS_2026_2027_ANNUAL_COUNTS.get(local_start.weekday())


def _canonical_paris_annual_dates(
    db: Session,
    *,
    school_year: str,
    group_id: UUID,
    template: CourseSession,
    course_type: CourseType,
    location: Location,
    accepted_dates: set[date],
) -> set[date]:
    """Prefer the reviewed live annual series when the quote is near its target.

    Historical accepted snapshots can contain one school-closure date while
    omitting the replacement teaching date. The live recurrence series is the
    source of truth only when it has exactly the reviewed annual volume and the
    quote itself is within one session of that volume. Short or partial-term
    quotes therefore keep their immutable accepted dates.
    """

    target = _paris_annual_target_count(
        school_year=school_year,
        course_type=course_type,
        location=location,
        template=template,
    )
    if target is None or abs(len(accepted_dates) - target) > 1:
        return accepted_dates
    local_template = template.start_at_utc.astimezone(_zone(template.timezone))
    live_rows = db.scalars(
        select(CourseSession).where(
            CourseSession.recurrence_group_id == group_id,
            CourseSession.course_type_id == template.course_type_id,
            CourseSession.location_id == template.location_id,
            CourseSession.status == SessionStatus.SCHEDULED,
            CourseSession.start_at_utc >= PARIS_2026_2027_START_UTC,
            CourseSession.start_at_utc < PARIS_2026_2027_END_UTC,
        )
    ).all()
    live_dates = {
        local.date()
        for row in live_rows
        for local in [row.start_at_utc.astimezone(_zone(row.timezone))]
        if local.weekday() == local_template.weekday()
        and local.strftime("%H:%M") == local_template.strftime("%H:%M")
    }
    return live_dates if len(live_dates) == target else accepted_dates


def _execution(followup: QuoteAcceptanceFollowup) -> dict[str, Any]:
    return _json_object(_json_object(followup.payload).get(EXECUTION_KEY))


def _transformation(followup: QuoteAcceptanceFollowup) -> dict[str, Any]:
    return _json_object(_json_object(followup.payload).get(TRANSFORMATION_KEY))


def _confirmed_variance_matches(
    payload: object,
    *,
    student_id: UUID,
    group_id: UUID,
    expected_sessions: int,
    booked_sessions: int,
) -> bool:
    """Return true only for a confirmation matching the current audit state.

    A confirmation is deliberately tied to the student, recurrence series and
    both compared counts.  If the planning changes again, the old decision no
    longer suppresses the audit warning.
    """

    row = _json_object(payload)
    return (
        _parse_uuid(row.get("student_id")) == student_id
        and _parse_uuid(row.get("series_id")) == group_id
        and _int_or_none(row.get("expected_sessions")) == expected_sessions
        and _int_or_none(row.get("booked_sessions")) == booked_sessions
    )


def _session_row_matches_template(row: dict[str, Any], template: CourseSession) -> bool:
    activity_id = _parse_uuid(row.get("activity_id"))
    if activity_id is not None and activity_id != template.course_type_id:
        return False
    location_id = _parse_uuid(row.get("location_id"))
    if location_id is not None and location_id != template.location_id:
        return False
    parsed = _parse_date(row.get("date") or row.get("start_date"))
    local_start = template.start_at_utc.astimezone(_zone(template.timezone))
    if parsed is not None and parsed.weekday() != local_start.weekday():
        return False
    raw_start = str(row.get("student_start_time") or row.get("start_time") or "").strip()
    if re.match(r"^\d{2}:\d{2}$", raw_start) and raw_start != local_start.strftime("%H:%M"):
        return False
    return True


def _expand_block_dates(row: dict[str, Any]) -> set[date]:
    start = _parse_date(row.get("start_date"))
    end = _parse_date(row.get("end_date"))
    if start is None:
        return set()
    if end is None:
        end = start
    try:
        weekday = int(row.get("weekday"))
    except (TypeError, ValueError):
        weekday = start.weekday()
    excluded = {
        parsed
        for field in ("holiday_dates", "closure_dates")
        for value in _json_list(row.get(field))
        if (parsed := _parse_date(value)) is not None
    }
    out: set[date] = set()
    cursor = start
    while cursor <= end:
        if cursor.weekday() == weekday and cursor not in excluded:
            out.add(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return out


def _expected_dates(
    quote: Quote,
    followup: QuoteAcceptanceFollowup,
    *,
    group_id: UUID,
    template: CourseSession,
    assigned_session_groups: dict[UUID, UUID],
) -> set[date]:
    snapshot = _json_object(quote.calendar_snapshot)
    transformation = _transformation(followup)
    schedule = _json_object(transformation.get("scheduleResolution"))
    assigned = _json_object(schedule.get("assignedSessionByActivityId"))
    schedule_keys = {
        str(key).strip()
        for key, session_id_raw in assigned.items()
        if (session_id := _parse_uuid(session_id_raw)) is not None
        and assigned_session_groups.get(session_id) == group_id
    }

    session_rows = [_json_object(row) for row in _json_list(snapshot.get("sessions"))]
    block_rows = [_json_object(row) for row in _json_list(snapshot.get("blocks"))]
    group_token = str(group_id)

    def matches_schedule(row: dict[str, Any]) -> bool:
        recommendation_key = str(row.get("recommendation_key") or "").strip()
        automatic_line = str(row.get("typeform_automatic_line") or "").strip()
        activity_id = str(row.get("activity_id") or "").strip()
        row_key = recommendation_key or (f"{activity_id}:{automatic_line}" if automatic_line else activity_id)
        return bool(schedule_keys and row_key in schedule_keys)

    def matches_group(row: dict[str, Any]) -> bool:
        return str(row.get("series_key") or row.get("recurrence_group_id") or "").strip() == group_token

    for predicate in (matches_schedule, matches_group):
        dates = {
            parsed
            for row in session_rows
            if predicate(row) and _session_row_matches_template(row, template)
            if (parsed := _parse_date(row.get("date"))) is not None
        }
        if dates:
            return dates
        block_dates: set[date] = set()
        for row in block_rows:
            if predicate(row) and _session_row_matches_template(row, template):
                block_dates.update(_expand_block_dates(row))
        if block_dates:
            return block_dates

    # Older accepted quotes do not always contain the live series key.  Only use
    # the activity/location/day/time signature when it resolves to one coherent
    # set of dates; parallel groups remain distinguishable through schedule keys.
    fallback_session_rows = [row for row in session_rows if _session_row_matches_template(row, template)]
    fallback_dates = {
        parsed
        for row in fallback_session_rows
        if (parsed := _parse_date(row.get("date"))) is not None
    }
    return fallback_dates


@dataclass
class AuditCandidate:
    quote: Quote
    followup: QuoteAcceptanceFollowup
    student: User
    group_id: UUID
    template: CourseSession
    course_type: CourseType
    location: Location
    bookings: list[Booking]
    sessions_by_booking_id: dict[UUID, CourseSession]
    expected_dates: set[date]
    invoice_lines_by_booking_id: dict[UUID, list[ClientInvoiceLine]]
    annual_invoice_expected: bool
    issue_codes: list[str]

    @property
    def current_dates(self) -> set[date]:
        return {
            session_obj.start_at_utc.astimezone(_zone(session_obj.timezone)).date()
            for session_obj in self.sessions_by_booking_id.values()
        }

    @property
    def repairable(self) -> bool:
        return (
            "PLANNING_DATE_MISMATCH" in self.issue_codes
            and len(self.bookings) == len(self.expected_dates)
            and len(self.current_dates) == len(self.bookings)
            and "INVOICE_AMOUNT_MISMATCH" not in self.issue_codes
            and "MISSING_INVOICE_LINE" not in self.issue_codes
        )

    @property
    def approved_for_automatic_repair(self) -> bool:
        return self.repairable and self.group_id in APPROVED_REPAIR_SERIES

    def public_dict(self) -> dict[str, Any]:
        tz = _zone(self.template.timezone)
        local_start = self.template.start_at_utc.astimezone(tz)
        current_dates = self.current_dates
        missing = sorted(self.expected_dates - current_dates)
        unexpected = sorted(current_dates - self.expected_dates)
        invoice_booking_count = sum(1 for booking in self.bookings if self.invoice_lines_by_booking_id.get(booking.id))
        return {
            "quote_id": str(self.quote.id),
            "quote_number": self.quote.quote_number,
            "student_id": str(self.student.id),
            "student_name": _display_name(self.student),
            "series_id": str(self.group_id),
            "activity_name": self.course_type.name,
            "location_name": self.location.name,
            "slot_label": local_start.strftime("%A %H:%M"),
            "issue_codes": self.issue_codes,
            "expected_sessions": len(self.expected_dates),
            "booked_sessions": len(self.bookings),
            "invoiced_sessions": invoice_booking_count,
            "expected_start": min(self.expected_dates).isoformat() if self.expected_dates else None,
            "expected_end": max(self.expected_dates).isoformat() if self.expected_dates else None,
            "booked_start": min(current_dates).isoformat() if current_dates else None,
            "booked_end": max(current_dates).isoformat() if current_dates else None,
            "missing_dates": [value.isoformat() for value in missing],
            "unexpected_dates": [value.isoformat() for value in unexpected],
            "repairable": self.repairable,
            "approved_for_automatic_repair": self.approved_for_automatic_repair,
        }


def _audit_candidates(db: Session, *, school_year: str) -> tuple[int, list[AuditCandidate]]:
    rows = db.execute(
        select(Quote, QuoteAcceptanceFollowup)
        .join(QuoteAcceptanceFollowup, QuoteAcceptanceFollowup.quote_id == Quote.id)
        .where(Quote.school_year_label == school_year)
        .order_by(Quote.created_at.asc())
    ).all()
    candidates: list[AuditCandidate] = []
    checked_quotes = 0
    quote_ids = [quote.id for quote, _ in rows]
    confirmed_variances_by_quote_id: dict[UUID, list[QuoteEvent]] = defaultdict(list)
    if quote_ids:
        for event in db.scalars(
            select(QuoteEvent).where(
                QuoteEvent.quote_id.in_(quote_ids),
                QuoteEvent.event_type == CONFIRMED_VARIANCE_EVENT,
            )
        ).all():
            confirmed_variances_by_quote_id[event.quote_id].append(event)

    for quote, followup in rows:
        execution = _execution(followup)
        if str(execution.get("status") or "").strip().lower() != "executed":
            continue
        booking_ids = [parsed for value in _json_list(execution.get("created_booking_ids")) if (parsed := _parse_uuid(value))]
        if not booking_ids:
            continue
        checked_quotes += 1
        booking_rows = db.execute(
            select(Booking, CourseSession, CourseType, Location)
            .join(CourseSession, CourseSession.id == Booking.session_id)
            .join(CourseType, CourseType.id == CourseSession.course_type_id)
            .join(Location, Location.id == CourseSession.location_id)
            .where(Booking.id.in_(booking_ids), Booking.status.in_(ACTIVE_BOOKING_STATUSES))
            .order_by(CourseSession.start_at_utc.asc())
        ).all()
        if not booking_rows:
            continue

        student_id = _parse_uuid(execution.get("student_client_id")) or quote.client_id or followup.target_client_id
        student = db.get(User, student_id) if student_id is not None else None
        if student is None:
            continue
        confirmed_variances = confirmed_variances_by_quote_id.get(quote.id, [])

        transformation = _transformation(followup)
        assigned = _json_object(_json_object(transformation.get("scheduleResolution")).get("assignedSessionByActivityId"))
        assigned_session_ids = [parsed for value in assigned.values() if (parsed := _parse_uuid(value))]
        assigned_session_groups = {
            row.id: row.recurrence_group_id
            for row in db.scalars(select(CourseSession).where(CourseSession.id.in_(assigned_session_ids))).all()
            if row.recurrence_group_id is not None
        } if assigned_session_ids else {}

        invoice_note_ids = [
            parsed
            for value in _json_list(execution.get("created_annual_invoice_note_ids"))
            if (parsed := _parse_uuid(value))
        ]
        # The invoice may have been issued after quote integration.  In that
        # case it is not part of ``created_annual_invoice_note_ids`` anymore,
        # but its immutable BOOKING source id still points to the enrollment.
        # Use that accounting reference instead of relying only on the quote's
        # historical note list.
        invoice_lines = list(
            db.scalars(
                select(ClientInvoiceLine).where(
                    ClientInvoiceLine.source == "BOOKING",
                    ClientInvoiceLine.source_payment_id.in_(booking_ids),
                )
            ).all()
        )
        invoice_lines_by_booking_id: dict[UUID, list[ClientInvoiceLine]] = defaultdict(list)
        for line in invoice_lines:
            invoice_lines_by_booking_id[line.source_payment_id].append(line)

        grouped: dict[UUID, list[tuple[Booking, CourseSession, CourseType, Location]]] = defaultdict(list)
        for booking, session_obj, course_type, location in booking_rows:
            if session_obj.recurrence_group_id is not None:
                grouped[session_obj.recurrence_group_id].append((booking, session_obj, course_type, location))

        for group_id, group_rows in grouped.items():
            template = group_rows[0][1]
            expected_dates = _expected_dates(
                quote,
                followup,
                group_id=group_id,
                template=template,
                assigned_session_groups=assigned_session_groups,
            )
            if not expected_dates:
                continue
            expected_dates = _canonical_paris_annual_dates(
                db,
                school_year=school_year,
                group_id=group_id,
                template=template,
                course_type=group_rows[0][2],
                location=group_rows[0][3],
                accepted_dates=expected_dates,
            )
            bookings = [row[0] for row in group_rows]
            sessions_by_booking_id = {row[0].id: row[1] for row in group_rows}
            current_dates = {
                row[1].start_at_utc.astimezone(_zone(row[1].timezone)).date()
                for row in group_rows
            }
            issue_codes: list[str] = []
            if len(bookings) != len(expected_dates):
                issue_codes.append("BOOKING_COUNT_MISMATCH")
            elif current_dates != expected_dates:
                issue_codes.append("PLANNING_DATE_MISMATCH")

            if invoice_note_ids or invoice_lines:
                if any(not invoice_lines_by_booking_id.get(booking.id) for booking in bookings):
                    issue_codes.append("MISSING_INVOICE_LINE")
                date_mismatch = False
                amount_mismatch = False
                for booking in bookings:
                    session_obj = sessions_by_booking_id[booking.id]
                    session_date = session_obj.start_at_utc.astimezone(_zone(session_obj.timezone)).date()
                    for line in invoice_lines_by_booking_id.get(booking.id, []):
                        if line.occurred_at.astimezone(_zone(session_obj.timezone)).date() != session_date:
                            date_mismatch = True
                        if (
                            _money(line.amount_excl_vat) != _money(booking.price_excl_vat_snapshot)
                            or _money(line.vat_amount) != _money(booking.vat_amount_snapshot)
                            or _money(line.total_incl_vat) != _money(booking.total_incl_vat_snapshot)
                        ):
                            amount_mismatch = True
                if date_mismatch:
                    issue_codes.append("INVOICE_DATE_MISMATCH")
                if amount_mismatch:
                    issue_codes.append("INVOICE_AMOUNT_MISMATCH")

            if issue_codes:
                if any(
                    _confirmed_variance_matches(
                        event.payload,
                        student_id=student.id,
                        group_id=group_id,
                        expected_sessions=len(expected_dates),
                        booked_sessions=len(bookings),
                    )
                    for event in confirmed_variances
                ):
                    continue
                candidates.append(
                    AuditCandidate(
                        quote=quote,
                        followup=followup,
                        student=student,
                        group_id=group_id,
                        template=template,
                        course_type=group_rows[0][2],
                        location=group_rows[0][3],
                        bookings=bookings,
                        sessions_by_booking_id=sessions_by_booking_id,
                        expected_dates=expected_dates,
                        invoice_lines_by_booking_id=invoice_lines_by_booking_id,
                        annual_invoice_expected=bool(invoice_note_ids or invoice_lines),
                        issue_codes=issue_codes,
                    )
                )

    return checked_quotes, candidates


def audit_quote_planning(db: Session, *, school_year: str = "2026-2027") -> dict[str, Any]:
    checked_quotes, candidates = _audit_candidates(db, school_year=school_year)
    return {
        "checked_at": datetime.now(timezone.utc),
        "school_year": school_year,
        "checked_quotes": checked_quotes,
        "affected_series": len({candidate.group_id for candidate in candidates}),
        "issue_count": len(candidates),
        "repairable_count": sum(1 for candidate in candidates if candidate.repairable),
        "approved_repair_count": sum(1 for candidate in candidates if candidate.approved_for_automatic_repair),
        "items": [candidate.public_dict() for candidate in candidates],
    }


def _copy_session(db: Session, *, template: CourseSession, target_date: date) -> CourseSession:
    tz = _zone(template.timezone)
    start_local = template.start_at_utc.astimezone(tz)
    end_local = template.end_at_utc.astimezone(tz)
    start_utc = datetime.combine(target_date, start_local.timetz().replace(tzinfo=None), tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(target_date, end_local.timetz().replace(tzinfo=None), tzinfo=tz).astimezone(timezone.utc)
    deadline_delta = template.start_at_utc - template.auto_cancel_deadline_utc
    session_obj = CourseSession(
        course_type_id=template.course_type_id,
        billing_entity_snapshot=template.billing_entity_snapshot,
        snapshot_seller_legal_entity_id=template.snapshot_seller_legal_entity_id,
        snapshot_payor_legal_entity_id=template.snapshot_payor_legal_entity_id,
        location_id=template.location_id,
        professor_id=template.professor_id,
        substitute_teacher_id=template.substitute_teacher_id,
        substitute_set_at=template.substitute_set_at,
        substitute_set_by=template.substitute_set_by,
        substitute_note=template.substitute_note,
        title=template.title,
        description=template.description,
        private_description=template.private_description,
        group_note=template.group_note,
        internal_note=template.internal_note,
        professor_reminder_note=template.professor_reminder_note,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        is_all_day=template.is_all_day,
        capacity_max=template.capacity_max,
        child_bookings_enabled=template.child_bookings_enabled,
        adult_bookings_enabled=template.adult_bookings_enabled,
        adult_capacity_max=template.adult_capacity_max,
        child_trial_bookings_enabled=template.child_trial_bookings_enabled,
        adult_trial_bookings_enabled=template.adult_trial_bookings_enabled,
        status=SessionStatus.SCHEDULED,
        auto_cancel_deadline_utc=start_utc - deadline_delta,
        auto_cancel_rule_enabled_override=template.auto_cancel_rule_enabled_override,
        auto_cancel_if_booked_less_than_override=template.auto_cancel_if_booked_less_than_override,
        auto_cancel_hours_before_start_override=template.auto_cancel_hours_before_start_override,
        zoom_link=template.zoom_link,
        is_private=template.is_private,
        allow_online_booking=template.allow_online_booking,
        visibility_scope=template.visibility_scope,
        booking_scope=template.booking_scope,
        external_booking_price_ttc=template.external_booking_price_ttc,
        external_booking_price_unit=template.external_booking_price_unit,
        show_external_remaining_seats=template.show_external_remaining_seats,
        timezone=template.timezone,
        recurrence_group_id=template.recurrence_group_id,
        recurrence_rule=template.recurrence_rule,
        recurrence_until_date=max(template.recurrence_until_date or target_date, target_date),
    )
    db.add(session_obj)
    db.flush()
    professor_rows = db.scalars(
        select(CourseSessionProfessor)
        .where(CourseSessionProfessor.session_id == template.id)
        .order_by(CourseSessionProfessor.position.asc())
    ).all()
    db.add_all(
        [
            CourseSessionProfessor(
                session_id=session_obj.id,
                professor_id=row.professor_id,
                position=row.position,
            )
            for row in professor_rows
        ]
    )
    return session_obj


def _move_optional_student_time(value: datetime | None, *, target_date: date, timezone_name: str) -> datetime | None:
    if value is None:
        return None
    tz = _zone(timezone_name)
    local = value.astimezone(tz)
    return datetime.combine(target_date, local.timetz().replace(tzinfo=None), tzinfo=tz).astimezone(timezone.utc)


def repair_safe_quote_planning_mismatches(
    db: Session,
    *,
    actor: User,
    school_year: str = "2026-2027",
) -> dict[str, Any]:
    _, candidates = _audit_candidates(db, school_year=school_year)
    repairable = [candidate for candidate in candidates if candidate.approved_for_automatic_repair]
    now = datetime.now(timezone.utc)
    created_sessions = 0
    moved_bookings = 0
    updated_invoice_lines = 0
    cancelled_sessions = 0
    repaired_quotes: set[UUID] = set()

    target_sessions: dict[tuple[UUID, date], CourseSession] = {}
    expected_by_group: dict[UUID, set[date]] = defaultdict(set)
    extra_dates_by_group: dict[UUID, set[date]] = defaultdict(set)
    template_by_group: dict[UUID, CourseSession] = {}

    for candidate in repairable:
        expected_by_group[candidate.group_id].update(candidate.expected_dates)
        extra_dates_by_group[candidate.group_id].update(candidate.current_dates - candidate.expected_dates)
        template_by_group.setdefault(candidate.group_id, candidate.template)

    for group_id, expected_dates in expected_by_group.items():
        group_sessions = list(
            db.scalars(
                select(CourseSession)
                .where(CourseSession.recurrence_group_id == group_id)
                .order_by(CourseSession.start_at_utc.asc())
                .with_for_update()
            ).all()
        )
        for session_obj in group_sessions:
            local_date = session_obj.start_at_utc.astimezone(_zone(session_obj.timezone)).date()
            if session_obj.status == SessionStatus.SCHEDULED:
                target_sessions[(group_id, local_date)] = session_obj
        for target_date in sorted(expected_dates):
            if (group_id, target_date) in target_sessions:
                continue
            created = _copy_session(db, template=template_by_group[group_id], target_date=target_date)
            target_sessions[(group_id, target_date)] = created
            created_sessions += 1

    for candidate in repairable:
        current_by_date = {
            session_obj.start_at_utc.astimezone(_zone(session_obj.timezone)).date(): booking
            for booking in candidate.bookings
            for session_obj in [candidate.sessions_by_booking_id[booking.id]]
        }
        extra_bookings = [current_by_date[value] for value in sorted(candidate.current_dates - candidate.expected_dates)]
        missing_dates = sorted(candidate.expected_dates - candidate.current_dates)
        if len(extra_bookings) != len(missing_dates):
            raise RuntimeError(f"Repair guard failed for quote {candidate.quote.quote_number}")

        for booking, target_date in zip(extra_bookings, missing_dates):
            target = target_sessions[(candidate.group_id, target_date)]
            duplicate = db.scalar(
                select(Booking.id).where(
                    Booking.session_id == target.id,
                    Booking.user_id == booking.user_id,
                    Booking.id != booking.id,
                )
            )
            if duplicate is not None:
                raise RuntimeError(f"Target booking already exists for quote {candidate.quote.quote_number}")
            capacity_count = int(
                db.scalar(
                    select(func.count(Booking.id)).where(
                        Booking.session_id == target.id,
                        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                    )
                )
                or 0
            )
            if capacity_count >= int(target.capacity_max or 0):
                raise RuntimeError(f"Target session is full for quote {candidate.quote.quote_number}")

            booking.session_id = target.id
            booking.student_start_at_utc = _move_optional_student_time(
                booking.student_start_at_utc,
                target_date=target_date,
                timezone_name=target.timezone,
            )
            booking.student_end_at_utc = _move_optional_student_time(
                booking.student_end_at_utc,
                target_date=target_date,
                timezone_name=target.timezone,
            )
            db.add(booking)
            ensure_booking_reminder(db, booking=booking, session_obj=target, now=now)
            for invoice_line in candidate.invoice_lines_by_booking_id.get(booking.id, []):
                invoice_line.occurred_at = target.start_at_utc
                db.add(invoice_line)
                updated_invoice_lines += 1
            moved_bookings += 1
            repaired_quotes.add(candidate.quote.id)

    db.flush()
    for group_id, extra_dates in extra_dates_by_group.items():
        for extra_date in sorted(extra_dates):
            session_obj = target_sessions.get((group_id, extra_date))
            if session_obj is None or session_obj.status != SessionStatus.SCHEDULED:
                continue
            active_count = int(
                db.scalar(
                    select(func.count(Booking.id)).where(
                        Booking.session_id == session_obj.id,
                        Booking.status.in_(ACTIVE_BOOKING_STATUSES),
                    )
                )
                or 0
            )
            if active_count == 0:
                session_obj.status = SessionStatus.CANCELLED
                session_obj.cancel_reason = "Correction automatique : date absente des devis validés"
                db.add(session_obj)
                cancelled_sessions += 1

    for group_id, expected_dates in expected_by_group.items():
        recurrence_end = max(expected_dates)
        for session_obj in db.scalars(
            select(CourseSession).where(
                CourseSession.recurrence_group_id == group_id,
                CourseSession.status == SessionStatus.SCHEDULED,
            )
        ).all():
            session_obj.recurrence_until_date = recurrence_end
            db.add(session_obj)

    for quote_id in repaired_quotes:
        db.add(
            QuoteEvent(
                quote_id=quote_id,
                event_type="planning_invoice_alignment_repaired",
                actor_type="admin",
                actor_id=actor.id,
                payload={
                    "school_year": school_year,
                    "reason": "Alignement sur les dates du devis validé; aucun e-mail envoyé",
                },
            )
        )

    db.commit()
    postcheck = audit_quote_planning(db, school_year=school_year)
    return {
        "school_year": school_year,
        "repaired_quotes": len(repaired_quotes),
        "created_sessions": created_sessions,
        "moved_bookings": moved_bookings,
        "updated_invoice_lines": updated_invoice_lines,
        "cancelled_sessions": cancelled_sessions,
        "remaining_issues": postcheck["issue_count"],
        "remaining_repairable": postcheck["repairable_count"],
        "remaining_approved_repairable": postcheck["approved_repair_count"],
    }
