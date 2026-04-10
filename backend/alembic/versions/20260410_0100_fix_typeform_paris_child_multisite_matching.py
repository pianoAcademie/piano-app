"""fix matching for Paris child 2026-2027 multisite Typeform config

Revision ID: 20260410_0100
Revises: 20260402_0099
Create Date: 2026-04-10 12:15:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260410_0100"
down_revision: Union[str, None] = "20260402_0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TARGET_SOURCE_CODE = "typeform_paris_child_2026_2027_multisite"
TARGET_FORM_ID = "G8eqpU6H"
FALLBACK_ACTIVITY_CODE = "PIANO_GROUP_ONSITE_1H"
ONSITE_WHEN = {
    "requested_course_mode": ["onsite", "presentiel", "ecole"],
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return list(parsed)
    return []


def _find_target_config(connection: sa.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        sa.text(
            """
            SELECT id, source_code, typeform_form_id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = :source_code
            LIMIT 1
            """
        ),
        {"source_code": TARGET_SOURCE_CODE},
    ).mappings().first()
    if row is not None:
        return dict(row)

    row = connection.execute(
        sa.text(
            """
            SELECT id, source_code, typeform_form_id, configuration_json
            FROM typeform_form_configs
            WHERE typeform_form_id = :form_id
            LIMIT 1
            """
        ),
        {"form_id": TARGET_FORM_ID},
    ).mappings().first()
    if row is not None:
        return dict(row)
    return None


def _first_existing_activity_code(config_json: dict[str, Any]) -> str | None:
    for item in _json_list(config_json.get("line_templates")):
        if not isinstance(item, dict):
            continue
        code = _text(item.get("activity_code"))
        if code:
            return code
    return None


def _active_activity_code(connection: sa.Connection, code: str) -> str | None:
    value = connection.execute(
        sa.text(
            """
            SELECT code
            FROM course_types
            WHERE active IS TRUE
              AND code = :code
            LIMIT 1
            """
        ),
        {"code": code},
    ).scalar()
    return _text(value) or None


def upgrade() -> None:
    connection = op.get_bind()
    target = _find_target_config(connection)
    if target is None:
        return

    config_json = _json_object(target.get("configuration_json"))
    activity_code = _first_existing_activity_code(config_json) or _active_activity_code(connection, FALLBACK_ACTIVITY_CODE)
    if not activity_code:
        return

    config_json["default_course_mode"] = "onsite"
    config_json["line_templates"] = [
        {
            "kind": "activity",
            "activity_code": activity_code,
            "quantity": "1",
            "when": ONSITE_WHEN,
        }
    ]

    table = sa.table(
        "typeform_form_configs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("configuration_json", postgresql.JSONB),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection.execute(
        sa.update(table)
        .where(table.c.id == target["id"])
        .values(
            configuration_json=config_json,
            updated_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    # Data-only fix: keep the safer matching in place.
    return None
