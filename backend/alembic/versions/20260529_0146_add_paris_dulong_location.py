"""add Paris Dulong location and calendars

Revision ID: 20260529_0146
Revises: 20260529_0145
Create Date: 2026-05-29 12:35:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260529_0146"
down_revision: Union[str, None] = "20260529_0145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CALENDAR_SETTING_KEY = "quote_school_calendars_v1"
DULONG_CODE = "DULONG"
DULONG_NAME = "Dulong"
DULONG_ADDRESS = "47 rue Dulong"
DULONG_CITY = "Paris"
PARIS_TEMPLATE_CODES = ("RICHELIEU", "POMPE", "SCHEFFER", "ASSAS")


def _load_calendars(connection: sa.Connection) -> list[dict[str, object]]:
    raw = connection.execute(
        sa.text("SELECT value FROM app_settings WHERE key = :key"),
        {"key": CALENDAR_SETTING_KEY},
    ).scalar()
    if not raw:
        return []
    try:
        parsed = json.loads(str(raw))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _save_calendars(connection: sa.Connection, calendars: list[dict[str, object]]) -> None:
    serialized = json.dumps(calendars, ensure_ascii=False)
    connection.execute(
        sa.text(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (:key, :value, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = now()
            """
        ),
        {"key": CALENDAR_SETTING_KEY, "value": serialized},
    )


def _upsert_dulong_calendars(connection: sa.Connection, dulong_id: object) -> None:
    calendars = _load_calendars(connection)
    if not calendars:
        calendars = []

    location_rows = connection.execute(
        sa.text(
            """
            SELECT id, code
            FROM locations
            WHERE code IN :codes
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": [*PARIS_TEMPLATE_CODES]},
    ).mappings().all()
    template_location_ids = {str(row["id"]) for row in location_rows}
    existing_dulong_years = {
        str(row.get("school_year_label") or "").strip()
        for row in calendars
        if str(row.get("location_id") or "") == str(dulong_id)
    }
    templates_by_year: dict[str, dict[str, object]] = {}
    for row in calendars:
        year = str(row.get("school_year_label") or "").strip()
        if not year or year in templates_by_year:
            continue
        if str(row.get("location_id") or "") not in template_location_ids:
            continue
        if not bool(row.get("is_active", True)):
            continue
        templates_by_year[year] = row

    now = datetime.now(timezone.utc).isoformat()
    for year, template in sorted(templates_by_year.items()):
        if year in existing_dulong_years:
            continue
        calendars.append(
            {
                "id": str(uuid4()),
                "name": f"Paris Dulong {year}",
                "school_year_label": year,
                "location_id": str(dulong_id),
                "vacation_periods": template.get("vacation_periods") if isinstance(template.get("vacation_periods"), list) else [],
                "holiday_dates": template.get("holiday_dates") if isinstance(template.get("holiday_dates"), list) else [],
                "closure_dates": template.get("closure_dates") if isinstance(template.get("closure_dates"), list) else [],
                "is_active": True,
                "deployment_status": "not_deployed",
                "deployment_last_at": None,
                "deployment_last_sync_at": None,
                "deployment_source_hash": None,
                "deployment_generated_count": 0,
                "deployment_generated_active_count": 0,
                "created_at": now,
                "updated_at": now,
            }
        )

    if "2026-2027" not in existing_dulong_years and "2026-2027" not in templates_by_year:
        calendars.append(
            {
                "id": str(uuid4()),
                "name": "Paris Dulong 2026-2027",
                "school_year_label": "2026-2027",
                "location_id": str(dulong_id),
                "vacation_periods": [],
                "holiday_dates": [],
                "closure_dates": [],
                "is_active": True,
                "deployment_status": "not_deployed",
                "deployment_last_at": None,
                "deployment_last_sync_at": None,
                "deployment_source_hash": None,
                "deployment_generated_count": 0,
                "deployment_generated_active_count": 0,
                "created_at": now,
                "updated_at": now,
            }
        )

    _save_calendars(connection, calendars)


def upgrade() -> None:
    connection = op.get_bind()
    dulong_id = connection.execute(
        sa.text(
            """
            INSERT INTO locations (code, name, address_line, city, country_code, is_online, timezone, active)
            VALUES (:code, :name, :address_line, :city, 'FR', false, 'Europe/Paris', true)
            ON CONFLICT (code) DO UPDATE
            SET name = EXCLUDED.name,
                address_line = EXCLUDED.address_line,
                city = EXCLUDED.city,
                country_code = EXCLUDED.country_code,
                is_online = EXCLUDED.is_online,
                timezone = EXCLUDED.timezone,
                active = true
            RETURNING id
            """
        ),
        {
            "code": DULONG_CODE,
            "name": DULONG_NAME,
            "address_line": DULONG_ADDRESS,
            "city": DULONG_CITY,
        },
    ).scalar_one()

    connection.execute(
        sa.text(
            """
            INSERT INTO planning_configs (location_id, description)
            VALUES (:location_id, :description)
            ON CONFLICT (location_id) DO UPDATE
            SET description = EXCLUDED.description,
                updated_at = now()
            """
        ),
        {"location_id": dulong_id, "description": DULONG_NAME},
    )

    connection.execute(
        sa.text(
            """
            WITH ranked_course_types AS (
                SELECT
                    id,
                    row_number() OVER (ORDER BY name ASC, code ASC) - 1 AS pos
                FROM course_types
                WHERE active IS TRUE
            )
            INSERT INTO planning_course_types (location_id, course_type_id, display_order)
            SELECT :location_id, ranked_course_types.id, ranked_course_types.pos
            FROM ranked_course_types
            ON CONFLICT (location_id, course_type_id) DO NOTHING
            """
        ),
        {"location_id": dulong_id},
    )

    _upsert_dulong_calendars(connection, dulong_id)


def downgrade() -> None:
    connection = op.get_bind()
    dulong_id = connection.execute(
        sa.text("SELECT id FROM locations WHERE code = :code"),
        {"code": DULONG_CODE},
    ).scalar()
    if dulong_id is not None:
        calendars = [
            row
            for row in _load_calendars(connection)
            if str(row.get("location_id") or "") != str(dulong_id)
        ]
        _save_calendars(connection, calendars)
        connection.execute(sa.text("DELETE FROM locations WHERE id = :id"), {"id": dulong_id})
