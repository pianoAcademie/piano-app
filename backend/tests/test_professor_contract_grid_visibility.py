from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.api.routes.professors import _filter_contract_grid_to_course_types, _school_year_bounds_for_day
from app.models.professor_contract import ProfessorContractLineMode
from app.schemas.professor import ProfessorContractGridLineOut, ProfessorContractGridOut


def _grid_with_course_types(*course_type_ids):
    return ProfessorContractGridOut(
        grid_id=uuid4(),
        valid_from=date(2026, 8, 1),
        valid_to=None,
        location_code=None,
        location_label="Configuration effective",
        notes=None,
        lines=[
            ProfessorContractGridLineOut(
                course_type_id=course_type_id,
                course_type_name=f"Course {index}",
                service_type=f"Course {index}",
                mode=ProfessorContractLineMode.PRESENTIEL,
                reference_duration_minutes=60,
                default_hourly_rate=Decimal("32.00"),
                rules=[],
            )
            for index, course_type_id in enumerate(course_type_ids)
        ],
    )


def test_contract_grid_only_keeps_planned_course_types() -> None:
    piano_id = uuid4()
    solfege_id = uuid4()
    grid = _grid_with_course_types(piano_id, solfege_id, None)

    visible = _filter_contract_grid_to_course_types(grid, course_type_ids={piano_id})

    assert [line.course_type_id for line in visible.lines] == [piano_id]
    assert len(grid.lines) == 3


def test_school_year_bounds_follow_august_boundary() -> None:
    assert _school_year_bounds_for_day(date(2026, 8, 2)) == (
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        datetime(2027, 8, 1, tzinfo=timezone.utc),
    )
    assert _school_year_bounds_for_day(date(2026, 7, 31)) == (
        datetime(2025, 8, 1, tzinfo=timezone.utc),
        datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
