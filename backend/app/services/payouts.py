from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseSession, CourseType, Location, Professor, SessionStatus
from app.models.payout import PayoutStatus, ProfessorHourlyRate, ProfessorSessionPayout
from app.services.professor_default_grid import (
    DefaultProfessorGridLine,
    load_default_professor_grid,
    resolve_default_professor_grid_hourly_rate,
)
from app.services.professor_contracts import resolve_professor_contract_rate_for_session


def _quantize_2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PayoutJobResult:
    checked: int
    created: int
    updated: int
    skipped_no_rate: int
    skipped_existing_locked: int


@dataclass(frozen=True)
class ResolvedHourlyRate:
    hourly_rate: Decimal
    currency_code: str


@dataclass(frozen=True)
class _ProfessorRateRule:
    min_students: int
    max_students: int | None
    hourly_rate: Decimal


def _effective_students_count(db: Session, *, session_id: UUID) -> int:
    count = db.scalar(
        select(func.count(Booking.id))
        .where(
            Booking.session_id == session_id,
            Booking.status.in_((BookingStatus.ATTENDED, BookingStatus.NO_SHOW)),
        )
    )
    return int(count or 0)


def _normalize_professor_rate_rules(raw_rules: object) -> list[_ProfessorRateRule]:
    if not isinstance(raw_rules, list):
        return []

    rules: list[_ProfessorRateRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        try:
            min_students = int(raw_rule.get("min_students"))
        except (TypeError, ValueError):
            continue
        if min_students < 0:
            continue

        max_students_raw = raw_rule.get("max_students")
        if max_students_raw is None:
            max_students: int | None = None
        else:
            try:
                max_students = int(max_students_raw)
            except (TypeError, ValueError):
                continue
            if max_students < min_students:
                continue

        try:
            hourly_rate = _quantize_2(Decimal(str(raw_rule.get("hourly_rate"))))
        except Exception:
            continue
        if hourly_rate < 0:
            continue
        rules.append(_ProfessorRateRule(min_students=min_students, max_students=max_students, hourly_rate=hourly_rate))

    rules.sort(key=lambda row: (row.min_students, row.max_students if row.max_students is not None else 10**9))
    return rules


def _resolve_professor_rate_hourly_value(
    db: Session,
    *,
    rate_row: ProfessorHourlyRate,
    session_id: UUID,
    effective_students_cache: dict[str, int],
    allow_headcount_rules: bool = True,
) -> Decimal | None:
    rules = _normalize_professor_rate_rules(rate_row.headcount_rules_json) if allow_headcount_rules else []
    if rules:
        if "value" not in effective_students_cache:
            effective_students_cache["value"] = _effective_students_count(db, session_id=session_id)
        effective_students_count = effective_students_cache["value"]
        for rule in rules:
            if effective_students_count < rule.min_students:
                continue
            if rule.max_students is not None and effective_students_count > rule.max_students:
                continue
            return _quantize_2(Decimal(rule.hourly_rate))

    if rate_row.hourly_rate is None:
        return None
    return _quantize_2(Decimal(rate_row.hourly_rate))


def _resolve_hourly_rate(
    db: Session,
    *,
    session_obj: CourseSession,
    on_date: date,
    professor_id_override: UUID | None = None,
    default_grid_lines: list[DefaultProfessorGridLine] | None = None,
) -> ResolvedHourlyRate | None:
    resolved_professor_id = professor_id_override if professor_id_override is not None else session_obj.professor_id
    if resolved_professor_id is None:
        return None

    course_type = db.scalar(select(CourseType).where(CourseType.id == session_obj.course_type_id))
    location = db.scalar(select(Location).where(Location.id == session_obj.location_id))

    base_filters = [
        ProfessorHourlyRate.professor_id == resolved_professor_id,
        ProfessorHourlyRate.valid_from <= on_date,
        or_(ProfessorHourlyRate.valid_to.is_(None), ProfessorHourlyRate.valid_to >= on_date),
    ]

    effective_students_cache: dict[str, int] = {}

    def _resolve_from_professor_override(
        rate_row: ProfessorHourlyRate | None,
        *,
        allow_headcount_rules: bool = True,
    ) -> ResolvedHourlyRate | None:
        if rate_row is None:
            return None
        resolved_hourly_rate = _resolve_professor_rate_hourly_value(
            db,
            rate_row=rate_row,
            session_id=session_obj.id,
            effective_students_cache=effective_students_cache,
            allow_headcount_rules=allow_headcount_rules,
        )
        if resolved_hourly_rate is None:
            return None
        return ResolvedHourlyRate(
            hourly_rate=resolved_hourly_rate,
            currency_code=rate_row.currency_code,
        )

    # 1) professor + course_type + location
    resolved = _resolve_from_professor_override(
        db.scalar(
            select(ProfessorHourlyRate)
            .where(
                *base_filters,
                ProfessorHourlyRate.course_type_id == session_obj.course_type_id,
                ProfessorHourlyRate.location_id == session_obj.location_id,
            )
            .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
            .limit(1)
        )
    )
    if resolved is not None:
        return resolved

    # 2) professor + course_type
    resolved = _resolve_from_professor_override(
        db.scalar(
            select(ProfessorHourlyRate)
            .where(
                *base_filters,
                ProfessorHourlyRate.course_type_id == session_obj.course_type_id,
                ProfessorHourlyRate.location_id.is_(None),
            )
            .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
            .limit(1)
        )
    )
    if resolved is not None:
        return resolved

    if course_type is not None:
        default_grid_rate = resolve_default_professor_grid_hourly_rate(
            db,
            session_id=session_obj.id,
            course_type_id=session_obj.course_type_id,
            preloaded_lines=default_grid_lines,
        )
        if default_grid_rate is not None:
            payout_currency = db.scalar(select(Professor.payout_currency).where(Professor.id == resolved_professor_id)) or "EUR"
            return ResolvedHourlyRate(
                hourly_rate=_quantize_2(Decimal(default_grid_rate)),
                currency_code=payout_currency.strip().upper() or "EUR",
            )

    # 3) professor global base rate (fallback only, without headcount rules)
    resolved = _resolve_from_professor_override(
        db.scalar(
            select(ProfessorHourlyRate)
            .where(
                *base_filters,
                ProfessorHourlyRate.course_type_id.is_(None),
                ProfessorHourlyRate.location_id.is_(None),
            )
            .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
            .limit(1)
        ),
        allow_headcount_rules=False,
    )
    if resolved is not None:
        return resolved

    # Legacy fallback: historic contract grids are evaluated only if no
    # collaborator override and no global default grid matched.
    if course_type is not None and location is not None:
        resolved_contract_rate = resolve_professor_contract_rate_for_session(
            db,
            professor_id=resolved_professor_id,
            session_id=session_obj.id,
            course_type=course_type,
            location=location,
            on_date=on_date,
        )
        if resolved_contract_rate is not None:
            payout_currency = db.scalar(select(Professor.payout_currency).where(Professor.id == resolved_professor_id)) or "EUR"
            return ResolvedHourlyRate(
                hourly_rate=_quantize_2(Decimal(resolved_contract_rate.hourly_rate)),
                currency_code=payout_currency.strip().upper() or "EUR",
            )

    # Fallback to activity-level default rate (referential), without overriding explicit collaborator rates.
    if course_type is None or course_type.default_hourly_rate is None:
        return None

    payout_currency = db.scalar(select(Professor.payout_currency).where(Professor.id == resolved_professor_id)) or "EUR"
    return ResolvedHourlyRate(
        hourly_rate=_quantize_2(Decimal(course_type.default_hourly_rate)),
        currency_code=payout_currency.strip().upper() or "EUR",
    )


def resolve_hourly_rate_for_session(
    db: Session,
    *,
    session_obj: CourseSession,
    on_date: date,
    professor_id_override: UUID | None = None,
    default_grid_lines: list[DefaultProfessorGridLine] | None = None,
) -> ResolvedHourlyRate | None:
    lines = default_grid_lines
    if lines is None:
        lines, _ = load_default_professor_grid(db)
    return _resolve_hourly_rate(
        db,
        session_obj=session_obj,
        on_date=on_date,
        professor_id_override=professor_id_override,
        default_grid_lines=lines,
    )


def resolve_hourly_rate_for_missing_service(
    db: Session,
    *,
    professor_id: UUID,
    course_type_id: UUID,
    location_id: UUID | None,
    on_date: date,
    attendees_count: int,
    default_grid_lines: list[DefaultProfessorGridLine] | None = None,
) -> ResolvedHourlyRate | None:
    safe_attendees = max(0, int(attendees_count))
    payout_currency = db.scalar(select(Professor.payout_currency).where(Professor.id == professor_id)) or "EUR"
    currency_code = payout_currency.strip().upper() or "EUR"

    base_filters = [
        ProfessorHourlyRate.professor_id == professor_id,
        ProfessorHourlyRate.valid_from <= on_date,
        or_(ProfessorHourlyRate.valid_to.is_(None), ProfessorHourlyRate.valid_to >= on_date),
    ]

    def _resolve_from_row(row: ProfessorHourlyRate | None, *, allow_headcount_rules: bool = True) -> ResolvedHourlyRate | None:
        if row is None:
            return None
        rules = _normalize_professor_rate_rules(row.headcount_rules_json) if allow_headcount_rules else []
        if rules:
            for rule in rules:
                if safe_attendees < rule.min_students:
                    continue
                if rule.max_students is not None and safe_attendees > rule.max_students:
                    continue
                return ResolvedHourlyRate(
                    hourly_rate=_quantize_2(Decimal(rule.hourly_rate)),
                    currency_code=(row.currency_code or currency_code).strip().upper() or currency_code,
                )
        if row.hourly_rate is None:
            return None
        return ResolvedHourlyRate(
            hourly_rate=_quantize_2(Decimal(row.hourly_rate)),
            currency_code=(row.currency_code or currency_code).strip().upper() or currency_code,
        )

    if location_id is not None:
        resolved = _resolve_from_row(
            db.scalar(
                select(ProfessorHourlyRate)
                .where(
                    *base_filters,
                    ProfessorHourlyRate.course_type_id == course_type_id,
                    ProfessorHourlyRate.location_id == location_id,
                )
                .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
                .limit(1)
            )
        )
        if resolved is not None:
            return resolved

    resolved = _resolve_from_row(
        db.scalar(
            select(ProfessorHourlyRate)
            .where(
                *base_filters,
                ProfessorHourlyRate.course_type_id == course_type_id,
                ProfessorHourlyRate.location_id.is_(None),
            )
            .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
            .limit(1)
        )
    )
    if resolved is not None:
        return resolved

    lines = default_grid_lines
    if lines is None:
        lines, _ = load_default_professor_grid(db)
    default_line = next((line for line in lines if line.course_type_id == course_type_id), None)
    if default_line is not None:
        for rule in default_line.rules:
            if safe_attendees < rule.min_students:
                continue
            if rule.max_students is not None and safe_attendees > rule.max_students:
                continue
            return ResolvedHourlyRate(
                hourly_rate=_quantize_2(Decimal(rule.hourly_rate)),
                currency_code=currency_code,
            )
        if default_line.default_hourly_rate is not None:
            return ResolvedHourlyRate(
                hourly_rate=_quantize_2(Decimal(default_line.default_hourly_rate)),
                currency_code=currency_code,
            )

    resolved = _resolve_from_row(
        db.scalar(
            select(ProfessorHourlyRate)
            .where(
                *base_filters,
                ProfessorHourlyRate.course_type_id.is_(None),
                ProfessorHourlyRate.location_id.is_(None),
            )
            .order_by(ProfessorHourlyRate.valid_from.desc(), ProfessorHourlyRate.created_at.desc())
            .limit(1)
        ),
        allow_headcount_rules=False,
    )
    if resolved is not None:
        return resolved

    course_type = db.scalar(select(CourseType).where(CourseType.id == course_type_id))
    if course_type is None or course_type.default_hourly_rate is None:
        return None
    return ResolvedHourlyRate(
        hourly_rate=_quantize_2(Decimal(course_type.default_hourly_rate)),
        currency_code=currency_code,
    )


def run_calc_professor_payouts_job(
    db: Session,
    *,
    now: datetime,
    limit: int = 200,
    force_recompute: bool = False,
) -> PayoutJobResult:
    payouts_sq = select(ProfessorSessionPayout.session_id).subquery()

    sessions_stmt = (
        select(CourseSession)
        .where(
            CourseSession.status != SessionStatus.CANCELLED,
            CourseSession.end_at_utc <= now,
            CourseSession.professor_id.is_not(None),
        )
        .order_by(CourseSession.end_at_utc.asc())
        .limit(limit)
        .with_for_update()
    )

    if not force_recompute:
        sessions_stmt = sessions_stmt.where(CourseSession.id.not_in(select(payouts_sq.c.session_id)))

    sessions = db.scalars(sessions_stmt).all()
    default_grid_lines, _ = load_default_professor_grid(db)

    created = 0
    updated = 0
    skipped_no_rate = 0
    skipped_existing_locked = 0

    for session_obj in sessions:
        session_date = session_obj.start_at_utc.date()
        rate = _resolve_hourly_rate(
            db,
            session_obj=session_obj,
            on_date=session_date,
            default_grid_lines=default_grid_lines,
        )
        if rate is None:
            skipped_no_rate += 1
            continue

        duration_hours = _quantize_2(
            Decimal((session_obj.end_at_utc - session_obj.start_at_utc).total_seconds()) / Decimal(3600)
        )
        hourly_rate = _quantize_2(Decimal(rate.hourly_rate))
        amount = _quantize_2(duration_hours * hourly_rate)

        payout = db.scalar(
            select(ProfessorSessionPayout)
            .where(ProfessorSessionPayout.session_id == session_obj.id)
            .with_for_update()
        )

        if payout is None:
            payout = ProfessorSessionPayout(
                session_id=session_obj.id,
                professor_id=session_obj.professor_id,
                duration_hours=duration_hours,
                hourly_rate_snapshot=hourly_rate,
                currency_snapshot=rate.currency_code,
                amount_snapshot=amount,
                payout_status=PayoutStatus.PENDING,
            )
            db.add(payout)
            created += 1
            continue

        if payout.payout_status == PayoutStatus.PAID:
            skipped_existing_locked += 1
            continue

        payout.professor_id = session_obj.professor_id
        payout.duration_hours = duration_hours
        payout.hourly_rate_snapshot = hourly_rate
        payout.currency_snapshot = rate.currency_code
        payout.amount_snapshot = amount
        if payout.payout_status not in (PayoutStatus.PENDING, PayoutStatus.APPROVED):
            payout.payout_status = PayoutStatus.PENDING
            payout.paid_at = None
        updated += 1

    return PayoutJobResult(
        checked=len(sessions),
        created=created,
        updated=updated,
        skipped_no_rate=skipped_no_rate,
        skipped_existing_locked=skipped_existing_locked,
    )
