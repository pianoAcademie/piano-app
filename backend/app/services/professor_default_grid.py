from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseType, DeliveryMode
from app.models.ops import AppSetting
from app.models.payout import ProfessorPayGridBracket, ProfessorPayGridPeriod, ProfessorPayGridRule

DEFAULT_PROFESSOR_GRID_SETTING_KEY = "config_professor_default_grid_v1"


@dataclass(frozen=True)
class DefaultProfessorGridRule:
    min_students: int
    max_students: int | None
    hourly_rate: Decimal


@dataclass(frozen=True)
class DefaultProfessorGridLine:
    course_type_id: UUID
    default_hourly_rate: Decimal | None
    rules: list[DefaultProfessorGridRule]


@dataclass(frozen=True)
class DefaultProfessorGridPeriodSnapshot:
    id: UUID
    start_date: date
    end_date: date | None
    status: str
    notes: str | None
    is_active: bool
    is_future: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    rules_count: int


def _quantize_rate(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if parsed < 0:
        return None
    return _quantize_rate(parsed)


def _as_int(value: object, *, min_value: int = 0) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < min_value:
        return None
    return parsed


def _normalize_rules(raw_rules: object) -> list[DefaultProfessorGridRule]:
    if not isinstance(raw_rules, list):
        return []

    parsed_rules: list[DefaultProfessorGridRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            continue
        min_students = _as_int(raw_rule.get("min_students"), min_value=0)
        max_students = raw_rule.get("max_students")
        max_students_value = _as_int(max_students, min_value=0) if max_students is not None else None
        hourly_rate = _as_decimal(raw_rule.get("hourly_rate"))
        if min_students is None or hourly_rate is None:
            continue
        if max_students_value is not None and max_students_value < min_students:
            continue
        parsed_rules.append(
            DefaultProfessorGridRule(
                min_students=min_students,
                max_students=max_students_value,
                hourly_rate=hourly_rate,
            )
        )

    parsed_rules.sort(key=lambda row: (row.min_students, row.max_students if row.max_students is not None else 10**9))
    return parsed_rules


def _normalize_lines(raw_lines: object) -> list[DefaultProfessorGridLine]:
    if not isinstance(raw_lines, list):
        return []

    out: list[DefaultProfessorGridLine] = []
    seen: set[UUID] = set()
    for raw_line in raw_lines:
        if not isinstance(raw_line, dict):
            continue
        try:
            course_type_id = UUID(str(raw_line.get("course_type_id")))
        except (TypeError, ValueError):
            continue
        if course_type_id in seen:
            continue
        seen.add(course_type_id)

        default_hourly_rate = _as_decimal(raw_line.get("default_hourly_rate"))
        rules = _normalize_rules(raw_line.get("rules"))
        if default_hourly_rate is None and not rules:
            continue

        out.append(
            DefaultProfessorGridLine(
                course_type_id=course_type_id,
                default_hourly_rate=default_hourly_rate,
                rules=rules,
            )
        )

    return out


def _serialize_legacy_lines(lines: list[DefaultProfessorGridLine]) -> str:
    serialized = {
        "lines": [
            {
                "course_type_id": str(line.course_type_id),
                "default_hourly_rate": (str(line.default_hourly_rate) if line.default_hourly_rate is not None else None),
                "rules": [
                    {
                        "min_students": rule.min_students,
                        "max_students": rule.max_students,
                        "hourly_rate": str(rule.hourly_rate),
                    }
                    for rule in line.rules
                ],
            }
            for line in lines
        ]
    }
    return json.dumps(serialized, separators=(",", ":"), ensure_ascii=True)


def _status_for_period(period: ProfessorPayGridPeriod, reference_date: date) -> str:
    raw_status = (period.status or "ACTIVE").strip().upper()
    if raw_status == "ARCHIVED":
        return "ARCHIVED"
    if period.start_date > reference_date:
        return "FUTURE"
    if period.end_date is not None and period.end_date < reference_date:
        return "ARCHIVED"
    return "ACTIVE"


def _snapshot_from_period(
    period: ProfessorPayGridPeriod,
    *,
    reference_date: date,
    rules_count: int = 0,
) -> DefaultProfessorGridPeriodSnapshot:
    resolved_status = _status_for_period(period, reference_date)
    return DefaultProfessorGridPeriodSnapshot(
        id=period.id,
        start_date=period.start_date,
        end_date=period.end_date,
        status=resolved_status,
        notes=period.notes,
        is_active=resolved_status == "ACTIVE",
        is_future=resolved_status == "FUTURE",
        is_archived=resolved_status == "ARCHIVED",
        created_at=period.created_at,
        updated_at=period.updated_at,
        rules_count=rules_count,
    )


def _mode_from_course_type(course_type: CourseType) -> str:
    if course_type.mode == DeliveryMode.ONLINE:
        return "EN_LIGNE"
    if course_type.mode == DeliveryMode.ONSITE:
        return "PRESENTIEL"
    return "AUTRE"


def _load_lines_for_period(db: Session, *, period_id: UUID) -> list[DefaultProfessorGridLine]:
    rule_rows = db.scalars(
        select(ProfessorPayGridRule)
        .where(ProfessorPayGridRule.period_id == period_id)
        .order_by(ProfessorPayGridRule.sort_order.asc(), ProfessorPayGridRule.created_at.asc())
    ).all()
    if not rule_rows:
        return []

    rule_ids = [row.id for row in rule_rows]
    bracket_rows = db.scalars(
        select(ProfessorPayGridBracket)
        .where(ProfessorPayGridBracket.rule_id.in_(rule_ids))
        .order_by(
            ProfessorPayGridBracket.rule_id.asc(),
            ProfessorPayGridBracket.sort_order.asc(),
            ProfessorPayGridBracket.min_students.asc(),
            ProfessorPayGridBracket.created_at.asc(),
        )
    ).all()

    brackets_by_rule: dict[UUID, list[DefaultProfessorGridRule]] = {rule_id: [] for rule_id in rule_ids}
    for bracket in bracket_rows:
        brackets_by_rule.setdefault(bracket.rule_id, []).append(
            DefaultProfessorGridRule(
                min_students=int(bracket.min_students),
                max_students=int(bracket.max_students) if bracket.max_students is not None else None,
                hourly_rate=_quantize_rate(Decimal(bracket.hourly_rate)),
            )
        )

    out: list[DefaultProfessorGridLine] = []
    for row in rule_rows:
        default_rate = _quantize_rate(Decimal(row.default_hourly_rate)) if row.default_hourly_rate is not None else None
        rules = brackets_by_rule.get(row.id, [])
        if default_rate is None and not rules:
            continue
        out.append(
            DefaultProfessorGridLine(
                course_type_id=row.course_type_id,
                default_hourly_rate=default_rate,
                rules=rules,
            )
        )
    return out


def _load_legacy_default_grid(db: Session) -> tuple[list[DefaultProfessorGridLine], datetime | None]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == DEFAULT_PROFESSOR_GRID_SETTING_KEY))
    if setting is None or not (setting.value or "").strip():
        return [], setting.updated_at if setting is not None else None

    try:
        payload = json.loads(setting.value)
    except json.JSONDecodeError:
        return [], setting.updated_at

    if not isinstance(payload, dict):
        return [], setting.updated_at

    lines = _normalize_lines(payload.get("lines"))
    return lines, setting.updated_at


def list_default_professor_grid_periods(
    db: Session,
    *,
    reference_date: date | None = None,
) -> list[DefaultProfessorGridPeriodSnapshot]:
    reference = reference_date or date.today()
    periods = db.scalars(
        select(ProfessorPayGridPeriod)
        .order_by(ProfessorPayGridPeriod.start_date.desc(), ProfessorPayGridPeriod.created_at.desc())
    ).all()
    if not periods:
        return []

    period_ids = [period.id for period in periods]
    rules_counts_rows = db.execute(
        select(ProfessorPayGridRule.period_id, func.count(ProfessorPayGridRule.id))
        .where(ProfessorPayGridRule.period_id.in_(period_ids))
        .group_by(ProfessorPayGridRule.period_id)
    ).all()
    rules_count_by_period_id = {period_id: int(count or 0) for period_id, count in rules_counts_rows}

    return [
        _snapshot_from_period(
            period,
            reference_date=reference,
            rules_count=rules_count_by_period_id.get(period.id, 0),
        )
        for period in periods
    ]


def get_default_professor_grid_period_snapshot(
    db: Session,
    *,
    period_id: UUID,
    reference_date: date | None = None,
) -> DefaultProfessorGridPeriodSnapshot | None:
    period = db.scalar(select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.id == period_id))
    if period is None:
        return None
    rules_count = db.scalar(
        select(func.count(ProfessorPayGridRule.id)).where(ProfessorPayGridRule.period_id == period_id)
    )
    return _snapshot_from_period(
        period,
        reference_date=reference_date or date.today(),
        rules_count=int(rules_count or 0),
    )


def load_default_professor_grid_for_period(
    db: Session,
    *,
    period_id: UUID,
) -> tuple[list[DefaultProfessorGridLine], datetime | None]:
    period = db.scalar(select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.id == period_id))
    if period is None:
        return [], None
    return _load_lines_for_period(db, period_id=period.id), period.updated_at


def _active_period_on_date(
    db: Session,
    *,
    on_date: date,
) -> ProfessorPayGridPeriod | None:
    return db.scalar(
        select(ProfessorPayGridPeriod)
        .where(
            ProfessorPayGridPeriod.status != "ARCHIVED",
            ProfessorPayGridPeriod.start_date <= on_date,
            or_(ProfessorPayGridPeriod.end_date.is_(None), ProfessorPayGridPeriod.end_date >= on_date),
        )
        .order_by(ProfessorPayGridPeriod.start_date.desc(), ProfessorPayGridPeriod.updated_at.desc())
        .limit(1)
    )


def load_default_professor_grid(
    db: Session,
    *,
    on_date: date | None = None,
) -> tuple[list[DefaultProfessorGridLine], datetime | None]:
    reference_date = on_date or date.today()
    active_period = _active_period_on_date(db, on_date=reference_date)
    if active_period is not None:
        lines = _load_lines_for_period(db, period_id=active_period.id)
        if lines:
            return lines, active_period.updated_at

    return _load_legacy_default_grid(db)


def _replace_lines_in_period(
    db: Session,
    *,
    period_id: UUID,
    lines: list[DefaultProfessorGridLine],
    currency_code: str,
) -> None:
    existing_rules = db.scalars(select(ProfessorPayGridRule).where(ProfessorPayGridRule.period_id == period_id)).all()
    existing_rule_ids = [row.id for row in existing_rules]
    if existing_rule_ids:
        db.execute(delete(ProfessorPayGridBracket).where(ProfessorPayGridBracket.rule_id.in_(existing_rule_ids)))
    db.execute(delete(ProfessorPayGridRule).where(ProfessorPayGridRule.period_id == period_id))

    if not lines:
        return

    course_type_ids = [line.course_type_id for line in lines]
    course_types = db.scalars(select(CourseType).where(CourseType.id.in_(course_type_ids))).all()
    course_type_by_id = {row.id: row for row in course_types}

    for line_index, line in enumerate(lines):
        course_type = course_type_by_id.get(line.course_type_id)
        if course_type is None:
            continue

        rule = ProfessorPayGridRule(
            period_id=period_id,
            course_type_id=line.course_type_id,
            mode=_mode_from_course_type(course_type),
            reference_duration_minutes=course_type.duration_minutes,
            currency_code=currency_code,
            default_hourly_rate=line.default_hourly_rate,
            sort_order=line_index,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(rule)
        db.flush()

        for bracket_index, bracket in enumerate(line.rules):
            db.add(
                ProfessorPayGridBracket(
                    rule_id=rule.id,
                    min_students=bracket.min_students,
                    max_students=bracket.max_students,
                    hourly_rate=bracket.hourly_rate,
                    sort_order=bracket_index,
                    updated_at=datetime.now(timezone.utc),
                )
            )


def _validate_period_overlap(
    db: Session,
    *,
    start_date: date,
    end_date: date | None,
    ignore_period_id: UUID | None = None,
) -> None:
    rows = db.scalars(
        select(ProfessorPayGridPeriod)
        .where(ProfessorPayGridPeriod.status != "ARCHIVED")
        .order_by(ProfessorPayGridPeriod.start_date.asc())
    ).all()

    for row in rows:
        if ignore_period_id is not None and row.id == ignore_period_id:
            continue
        row_start = row.start_date
        row_end = row.end_date

        if row_end is not None and row_end < start_date:
            continue
        if end_date is not None and row_start > end_date:
            continue

        if row_end is None or end_date is None:
            raise ValueError("Default grid periods cannot overlap")

        if row_start <= end_date and row_end >= start_date:
            raise ValueError("Default grid periods cannot overlap")


def create_default_professor_grid_period(
    db: Session,
    *,
    start_date: date,
    end_date: date | None,
    notes: str | None,
    clone_from_period_id: UUID | None = None,
) -> ProfessorPayGridPeriod:
    if end_date is not None and end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    _validate_period_overlap(db, start_date=start_date, end_date=end_date)

    reference = date.today()
    status = "FUTURE" if start_date > reference else "ACTIVE"
    now = datetime.now(timezone.utc)
    period = ProfessorPayGridPeriod(
        start_date=start_date,
        end_date=end_date,
        status=status,
        notes=notes,
        updated_at=now,
    )
    db.add(period)
    db.flush()

    if clone_from_period_id is not None:
        clone_lines, _ = load_default_professor_grid_for_period(db, period_id=clone_from_period_id)
        _replace_lines_in_period(db, period_id=period.id, lines=clone_lines, currency_code="EUR")
    else:
        existing_periods_count = db.scalar(select(func.count(ProfessorPayGridPeriod.id)))
        if int(existing_periods_count or 0) == 1:
            legacy_lines, _ = _load_legacy_default_grid(db)
            if legacy_lines:
                _replace_lines_in_period(db, period_id=period.id, lines=legacy_lines, currency_code="EUR")

    return period


def update_default_professor_grid_period(
    db: Session,
    *,
    period_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    notes: str | None = None,
    status: str | None = None,
) -> ProfessorPayGridPeriod | None:
    period = db.scalar(select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.id == period_id))
    if period is None:
        return None

    next_start = start_date or period.start_date
    next_end = end_date if end_date is not None else period.end_date

    if next_end is not None and next_end < next_start:
        raise ValueError("end_date must be >= start_date")

    _validate_period_overlap(db, start_date=next_start, end_date=next_end, ignore_period_id=period.id)

    period.start_date = next_start
    period.end_date = next_end
    if notes is not None:
        period.notes = notes
    if status is not None and status.strip():
        period.status = status.strip().upper()
    period.updated_at = datetime.now(timezone.utc)
    db.add(period)
    return period


def archive_default_professor_grid_period(
    db: Session,
    *,
    period_id: UUID,
) -> ProfessorPayGridPeriod | None:
    period = db.scalar(select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.id == period_id))
    if period is None:
        return None
    period.status = "ARCHIVED"
    period.updated_at = datetime.now(timezone.utc)
    db.add(period)
    return period


def save_default_professor_grid_for_period(
    db: Session,
    *,
    period_id: UUID,
    lines: list[DefaultProfessorGridLine],
    currency_code: str = "EUR",
) -> datetime:
    period = db.scalar(select(ProfessorPayGridPeriod).where(ProfessorPayGridPeriod.id == period_id))
    if period is None:
        raise ValueError("Period not found")

    _replace_lines_in_period(
        db,
        period_id=period.id,
        lines=lines,
        currency_code=(currency_code or "EUR").strip().upper() or "EUR",
    )
    now = datetime.now(timezone.utc)
    period.updated_at = now
    db.add(period)
    return now


def save_default_professor_grid(
    db: Session,
    *,
    lines: list[DefaultProfessorGridLine],
) -> datetime:
    reference = date.today()
    period = _active_period_on_date(db, on_date=reference)
    if period is None:
        period = ProfessorPayGridPeriod(
            start_date=reference,
            end_date=None,
            status="ACTIVE",
            notes="Migration depuis la configuration legacy",
            updated_at=datetime.now(timezone.utc),
        )
        db.add(period)
        db.flush()

    now = save_default_professor_grid_for_period(db, period_id=period.id, lines=lines, currency_code="EUR")

    serialized = _serialize_legacy_lines(lines)
    setting = db.scalar(select(AppSetting).where(AppSetting.key == DEFAULT_PROFESSOR_GRID_SETTING_KEY))
    if setting is None:
        setting = AppSetting(key=DEFAULT_PROFESSOR_GRID_SETTING_KEY, value=serialized, updated_at=now)
    else:
        setting.value = serialized
        setting.updated_at = now
    db.add(setting)

    return now


def _effective_students_count(db: Session, *, session_id: UUID) -> int:
    count = db.scalar(
        select(func.count(Booking.id)).where(
            Booking.session_id == session_id,
            Booking.status.in_((BookingStatus.ATTENDED, BookingStatus.NO_SHOW)),
        )
    )
    return int(count or 0)


def resolve_default_professor_grid_hourly_rate(
    db: Session,
    *,
    session_id: UUID,
    course_type_id: UUID,
    preloaded_lines: list[DefaultProfessorGridLine] | None = None,
) -> Decimal | None:
    lines = preloaded_lines
    if lines is None:
        lines, _ = load_default_professor_grid(db)

    target_line = next((line for line in lines if line.course_type_id == course_type_id), None)
    if target_line is None:
        return None

    effective_students_count = _effective_students_count(db, session_id=session_id)
    for rule in target_line.rules:
        if effective_students_count < rule.min_students:
            continue
        if rule.max_students is not None and effective_students_count > rule.max_students:
            continue
        return _quantize_rate(Decimal(rule.hourly_rate))

    if target_line.default_hourly_rate is None:
        return None
    return _quantize_rate(Decimal(target_line.default_hourly_rate))
