"""fix Paris eveil 2026 Typeform initiation line template

Revision ID: 20260520_0131
Revises: 20260520_0130
Create Date: 2026-05-20 14:05:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0131"
down_revision: Union[str, None] = "20260520_0130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODES = (
    "typeform_paris_eveil_2026_2027_multisite",
    "TYPEFORM_PARIS_EVEIL_2026_2027_MULTISITE",
)
TYPEFORM_FORM_IDS = ("UZPGEkmi",)
INITIATION_ACTIVITY_CODE = "ACT_INITIATION_AU_PIANO_E9BD5B"
EVEIL_ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"


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


def _build_line_templates(activity_code: str) -> list[dict[str, object]]:
    return [
        {
            "kind": "activity",
            "activity_code": activity_code,
            "quantity": "1",
        }
    ]


def _preferred_activity_code(connection: sa.Connection) -> str:
    existing = connection.execute(
        sa.text(
            """
            SELECT code
            FROM course_types
            WHERE code = ANY(:codes)
            ORDER BY CASE code
                WHEN :initiation_code THEN 0
                WHEN :eveil_code THEN 1
                ELSE 2
            END
            LIMIT 1
            """
        ),
        {
            "codes": [INITIATION_ACTIVITY_CODE, EVEIL_ACTIVITY_CODE],
            "initiation_code": INITIATION_ACTIVITY_CODE,
            "eveil_code": EVEIL_ACTIVITY_CODE,
        },
    ).scalar()
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    fallback = connection.execute(
        sa.text(
            """
            SELECT code
            FROM course_types
            WHERE active IS TRUE
              AND (
                    lower(name) LIKE '%initiation%'
                 OR lower(name) LIKE '%eveil%'
                 OR lower(name) LIKE '%éveil%'
              )
            ORDER BY CASE
                WHEN lower(name) LIKE '%initiation%' THEN 0
                ELSE 1
            END, name
            LIMIT 1
            """
        )
    ).scalar()
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return INITIATION_ACTIVITY_CODE


def _update_configs(*, downgrade: bool = False) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = ANY(:source_codes)
               OR typeform_form_id = ANY(:form_ids)
            """
        ),
        {"source_codes": list(SOURCE_CODES), "form_ids": list(TYPEFORM_FORM_IDS)},
    ).mappings().all()
    if not rows:
        return

    activity_code = _preferred_activity_code(connection)
    for row in rows:
        config = _json_object(row.get("configuration_json"))
        if downgrade:
            config["line_templates"] = []
        else:
            config["label"] = config.get("label") or "Paris Eveil musical 2026-2027"
            config["default_course_mode"] = "onsite"
            config["line_templates"] = _build_line_templates(activity_code)

        connection.execute(
            sa.text(
                """
                UPDATE typeform_form_configs
                SET configuration_json = CAST(:configuration_json AS jsonb),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": row["id"], "configuration_json": json.dumps(config, ensure_ascii=True)},
        )


def upgrade() -> None:
    _update_configs()


def downgrade() -> None:
    _update_configs(downgrade=True)
