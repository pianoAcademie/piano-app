"""force Paris teen collective Typeform activity mapping

Revision ID: 20260517_0121
Revises: 20260517_0120
Create Date: 2026-05-17 17:20:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260517_0121"
down_revision: Union[str, None] = "20260517_0120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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


def _is_collective_template(raw_template: dict[str, Any]) -> bool:
    when = raw_template.get("when")
    mode_values = [str(item).strip().lower() for item in (when.get("requested_course_mode", []) if isinstance(when, dict) else [])]
    title = str(raw_template.get("title") or raw_template.get("activity_name") or "").strip().lower()
    code = str(raw_template.get("activity_code") or "").strip().upper()
    return (
        "cours collectif" in mode_values
        or "cours collectif" in title
        or "cours collectifs ado" in title
        or code in {"ACT_COURS_COLLECTIF_ADULTE_2342BD", "ACT_COURS_COLLECTIFS_ADO_ADULTES_394F7E"}
    )


def _patch_configuration(configuration: dict[str, Any]) -> bool:
    templates = configuration.get("line_templates")
    if not isinstance(templates, list):
        return False
    changed = False
    for raw_template in templates:
        if not isinstance(raw_template, dict):
            continue
        if raw_template.get("kind") != "activity" or not _is_collective_template(raw_template):
            continue
        if raw_template.get("activity_code") != NEW_COLLECTIVE_ACTIVITY_CODE:
            raw_template["activity_code"] = NEW_COLLECTIVE_ACTIVITY_CODE
            changed = True
        if raw_template.pop("activity_id", None) is not None:
            changed = True
    return changed


def upgrade() -> None:
    connection = op.get_bind()
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
        {"source_codes": list(TARGET_SOURCE_CODES), "form_ids": list(TARGET_FORM_IDS)},
    ).mappings().all()
    for row in rows:
        configuration = _json_object(row["configuration_json"])
        if not _patch_configuration(configuration):
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
            {"id": row["id"], "configuration_json": json.dumps(configuration, ensure_ascii=True)},
        )


def downgrade() -> None:
    pass
