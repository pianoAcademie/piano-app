"""fix Paris teen collective Typeform activity mapping

Revision ID: 20260517_0120
Revises: 20260517_0119
Create Date: 2026-05-17 17:05:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_0120"
down_revision: Union[str, None] = "20260517_0119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_COLLECTIVE_ACTIVITY_CODE = "ACT_COURS_COLLECTIF_ADULTE_2342BD"
NEW_COLLECTIVE_ACTIVITY_CODE = "ACT_COURS_COLLECTIFS_ADO_ADULTES_394F7E"
TARGET_SOURCE_CODES = (
    "typeform_paris_teen_2026_2027_multisite",
    "typeform_paris_adult_2026_2027_multisite",
)
TARGET_FORM_IDS = (
    "hnX4kqpY",
    "XXTa2w7l",
)


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


def _patch_collective_activity(configuration: dict[str, Any], *, next_code: str) -> bool:
    changed = False
    templates = configuration.get("line_templates")
    if not isinstance(templates, list):
        return False
    for raw_template in templates:
        if not isinstance(raw_template, dict):
            continue
        if raw_template.get("kind") != "activity":
            continue
        if raw_template.get("activity_code") != OLD_COLLECTIVE_ACTIVITY_CODE:
            continue
        when = raw_template.get("when")
        if isinstance(when, dict) and "Cours collectif" not in [str(item) for item in when.get("requested_course_mode", [])]:
            continue
        raw_template["activity_code"] = next_code
        changed = True
    return changed


def _update_configs(connection: sa.Connection, *, next_code: str) -> None:
    stmt = sa.text(
        """
        SELECT id, configuration_json
        FROM typeform_form_configs
        WHERE source_code IN :source_codes
           OR typeform_form_id IN :form_ids
        """
    ).bindparams(
        sa.bindparam("source_codes", expanding=True),
        sa.bindparam("form_ids", expanding=True),
    )
    rows = connection.execute(
        stmt,
        {
            "source_codes": list(TARGET_SOURCE_CODES),
            "form_ids": list(TARGET_FORM_IDS),
        },
    ).mappings().all()
    for row in rows:
        configuration = _json_object(row["configuration_json"])
        if not _patch_collective_activity(configuration, next_code=next_code):
            continue
        connection.execute(
            sa.text(
                """
                UPDATE typeform_form_configs
                SET configuration_json = CAST(:configuration_json AS jsonb),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "configuration_json": json.dumps(configuration, ensure_ascii=True),
            },
        )


def upgrade() -> None:
    _update_configs(op.get_bind(), next_code=NEW_COLLECTIVE_ACTIVITY_CODE)


def downgrade() -> None:
    _update_configs(op.get_bind(), next_code=OLD_COLLECTIVE_ACTIVITY_CODE)
