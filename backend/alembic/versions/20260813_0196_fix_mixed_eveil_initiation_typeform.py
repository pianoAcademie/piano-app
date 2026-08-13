"""route mixed Eveil / Initiation Typeform responses by answered branch

Revision ID: 20260813_0196
Revises: 20260812_0195
Create Date: 2026-08-13 09:00:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0196"
down_revision: Union[str, None] = "20260812_0195"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODES = (
    "typeform_paris_eveil_2026_2027_multisite",
    "TYPEFORM_PARIS_EVEIL_2026_2027_MULTISITE",
)
TYPEFORM_FORM_IDS = ("UZPGEkmi",)
EVEIL_ACTIVITY_CODE = "ACT_EVEIL_MUSICAL_98E099"
INITIATION_ACTIVITY_CODE = "ACT_INITIATION_AU_PIANO_E9BD5B"


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


def _activity_exists(connection: sa.Connection, code: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT 1 FROM course_types WHERE code = :code LIMIT 1"),
            {"code": code},
        ).scalar()
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _activity_exists(connection, EVEIL_ACTIVITY_CODE):
        return

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

    for row in rows:
        config = _json_object(row.get("configuration_json"))
        line_templates: list[dict[str, object]] = [
            {
                "kind": "activity",
                "activity_code": EVEIL_ACTIVITY_CODE,
                "quantity": "1",
                "when": {"requested_activity_type": "eveil"},
            }
        ]
        if _activity_exists(connection, INITIATION_ACTIVITY_CODE):
            line_templates.append(
                {
                    "kind": "activity",
                    "activity_code": INITIATION_ACTIVITY_CODE,
                    "quantity": "1",
                    "when": {"requested_activity_type": "initiation"},
                }
            )
        config["label"] = "Paris Eveil musical / Initiation 2026-2027"
        config["line_templates"] = line_templates

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
                "configuration_json": json.dumps(config, ensure_ascii=True),
            },
        )


def downgrade() -> None:
    pass
