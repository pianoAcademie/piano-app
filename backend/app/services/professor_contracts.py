from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Booking, BookingStatus, CourseType, DeliveryMode, Location
from app.models.professor_contract import (
    ProfessorContractGrid,
    ProfessorContractGridLine,
    ProfessorContractGridLineRule,
    ProfessorContractLineMode,
)

CONTRACT_LOCATION_OPTIONS: list[tuple[str, str]] = [
    ("PARIS", "Paris"),
    ("BAR_LE_DUC", "Bar-le-Duc"),
    ("LYON", "Lyon"),
    ("MARSEILLE", "Marseille"),
    ("LILLE", "Lille"),
    ("STRASBOURG", "Strasbourg"),
    ("NANTES", "Nantes"),
    ("TOULOUSE", "Toulouse"),
    ("BORDEAUX", "Bordeaux"),
    ("AUTRE_PROVINCE", "Autre province"),
]
CONTRACT_LOCATION_CODES: set[str] = {code for code, _ in CONTRACT_LOCATION_OPTIONS}


@dataclass(frozen=True)
class ResolvedContractRate:
    hourly_rate: Decimal
    grid_id: UUID
    line_id: UUID
    rule_id: UUID | None
    effective_students_count: int
    mode: ProfessorContractLineMode
    location_mismatch: bool


def normalize_contract_location_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = raw.strip().upper()
    if not normalized:
        return None
    if normalized not in CONTRACT_LOCATION_CODES:
        raise ValueError(f"Unsupported location code: {normalized}")
    return normalized


def label_for_contract_location(code: str | None) -> str:
    if code is None:
        return "Tous lieux"
    for item_code, label in CONTRACT_LOCATION_OPTIONS:
        if item_code == code:
            return label
    return code


def contract_mode_from_session(course_type: CourseType, location: Location) -> ProfessorContractLineMode:
    base_mode = contract_mode_from_course_type(course_type)
    if base_mode != ProfessorContractLineMode.AUTRE:
        return base_mode
    if bool(location.is_online):
        return ProfessorContractLineMode.EN_LIGNE
    return ProfessorContractLineMode.AUTRE


def contract_mode_from_course_type(course_type: CourseType) -> ProfessorContractLineMode:
    if course_type.mode == DeliveryMode.ONLINE:
        return ProfessorContractLineMode.EN_LIGNE
    if course_type.mode == DeliveryMode.ONSITE:
        return ProfessorContractLineMode.PRESENTIEL
    return ProfessorContractLineMode.AUTRE


def contract_location_code_from_location(location: Location) -> str | None:
    location_code = (location.code or "").strip().upper()
    if location_code in CONTRACT_LOCATION_CODES:
        return location_code
    return None


def list_professor_contract_grids(
    db: Session,
    *,
    professor_id: UUID,
) -> list[ProfessorContractGrid]:
    return db.scalars(
        select(ProfessorContractGrid)
        .where(ProfessorContractGrid.professor_id == professor_id)
        .order_by(ProfessorContractGrid.valid_from.desc(), ProfessorContractGrid.created_at.desc())
    ).all()


def find_professor_contract_grids_on_date(
    db: Session,
    *,
    professor_id: UUID,
    on_date: date,
) -> list[ProfessorContractGrid]:
    return db.scalars(
        select(ProfessorContractGrid)
        .where(
            ProfessorContractGrid.professor_id == professor_id,
            ProfessorContractGrid.valid_from <= on_date,
            or_(ProfessorContractGrid.valid_to.is_(None), ProfessorContractGrid.valid_to >= on_date),
        )
        .order_by(ProfessorContractGrid.valid_from.desc(), ProfessorContractGrid.created_at.desc())
    ).all()


def _line_lookup_key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _line_for_course_type(
    lines: list[ProfessorContractGridLine],
    *,
    course_type: CourseType,
    expected_mode: ProfessorContractLineMode,
) -> ProfessorContractGridLine | None:
    direct_mode_match = [
        row for row in lines if row.course_type_id == course_type.id and row.mode == expected_mode
    ]
    if direct_mode_match:
        return direct_mode_match[0]

    direct_match = [row for row in lines if row.course_type_id == course_type.id]
    if direct_match:
        return direct_match[0]

    expected_key = _line_lookup_key(course_type.name)
    mode_lines = [row for row in lines if row.mode == expected_mode]
    for row in mode_lines:
        if _line_lookup_key(row.service_type) == expected_key:
            return row

    for row in mode_lines:
        if row.service_type.strip().casefold() == "autre":
            return row

    for row in lines:
        if _line_lookup_key(row.service_type) == expected_key:
            return row

    return None


def _effective_students_count(db: Session, *, session_id: UUID) -> int:
    count = db.scalar(
        select(func.count(Booking.id))
        .where(
            Booking.session_id == session_id,
            Booking.status.in_((BookingStatus.ATTENDED, BookingStatus.NO_SHOW)),
        )
    )
    return int(count or 0)


def _select_rule_for_headcount(
    rules: list[ProfessorContractGridLineRule],
    *,
    effective_students_count: int,
) -> ProfessorContractGridLineRule | None:
    for row in rules:
        max_value = row.max_students
        if effective_students_count < row.min_students:
            continue
        if max_value is not None and effective_students_count > max_value:
            continue
        return row
    return None


def resolve_professor_contract_rate_for_session(
    db: Session,
    *,
    professor_id: UUID,
    session_id: UUID,
    course_type: CourseType,
    location: Location,
    on_date: date,
) -> ResolvedContractRate | None:
    valid_grids = find_professor_contract_grids_on_date(db, professor_id=professor_id, on_date=on_date)
    if not valid_grids:
        return None

    expected_mode = contract_mode_from_session(course_type, location)
    expected_location_code = contract_location_code_from_location(location)

    candidate_grids: list[ProfessorContractGrid]
    location_mismatch = False

    if expected_mode == ProfessorContractLineMode.PRESENTIEL:
        candidate_grids = [row for row in valid_grids if row.location_code == expected_location_code]
        if not candidate_grids:
            candidate_grids = [row for row in valid_grids if row.location_code is None]
            location_mismatch = True if candidate_grids else False
    else:
        candidate_grids = valid_grids

    if not candidate_grids:
        return None

    selected_grid = candidate_grids[0]
    lines = db.scalars(
        select(ProfessorContractGridLine)
        .where(ProfessorContractGridLine.grid_id == selected_grid.id)
        .order_by(ProfessorContractGridLine.display_order.asc(), ProfessorContractGridLine.created_at.asc())
    ).all()
    if not lines:
        return None

    line = _line_for_course_type(lines, course_type=course_type, expected_mode=expected_mode)
    if line is None:
        return None

    rules = db.scalars(
        select(ProfessorContractGridLineRule)
        .where(ProfessorContractGridLineRule.line_id == line.id)
        .order_by(
            ProfessorContractGridLineRule.display_order.asc(),
            ProfessorContractGridLineRule.min_students.asc(),
            ProfessorContractGridLineRule.created_at.asc(),
        )
    ).all()
    effective_students_count = _effective_students_count(db, session_id=session_id)
    selected_rule = _select_rule_for_headcount(rules, effective_students_count=effective_students_count)

    if selected_rule is not None:
        return ResolvedContractRate(
            hourly_rate=Decimal(selected_rule.hourly_rate),
            grid_id=selected_grid.id,
            line_id=line.id,
            rule_id=selected_rule.id,
            effective_students_count=effective_students_count,
            mode=expected_mode,
            location_mismatch=location_mismatch,
        )

    if line.default_hourly_rate is None:
        return None

    return ResolvedContractRate(
        hourly_rate=Decimal(line.default_hourly_rate),
        grid_id=selected_grid.id,
        line_id=line.id,
        rule_id=None,
        effective_students_count=effective_students_count,
        mode=expected_mode,
        location_mismatch=location_mismatch,
    )
