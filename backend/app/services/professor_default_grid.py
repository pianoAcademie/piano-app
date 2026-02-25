from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus
from app.models.ops import AppSetting

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


def load_default_professor_grid(db: Session) -> tuple[list[DefaultProfessorGridLine], datetime | None]:
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


def save_default_professor_grid(
    db: Session,
    *,
    lines: list[DefaultProfessorGridLine],
) -> datetime:
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

    now = datetime.now(timezone.utc)
    setting = db.scalar(select(AppSetting).where(AppSetting.key == DEFAULT_PROFESSOR_GRID_SETTING_KEY))
    if setting is None:
        setting = AppSetting(
            key=DEFAULT_PROFESSOR_GRID_SETTING_KEY,
            value=json.dumps(serialized, separators=(",", ":"), ensure_ascii=True),
            updated_at=now,
        )
        db.add(setting)
        return now

    setting.value = json.dumps(serialized, separators=(",", ":"), ensure_ascii=True)
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
