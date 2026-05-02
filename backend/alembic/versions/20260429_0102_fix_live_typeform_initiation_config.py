"""repair live Typeform initiation form config

Revision ID: 20260429_0102
Revises: 20260422_0101
Create Date: 2026-04-29 18:35:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260429_0102"
down_revision: Union[str, None] = "20260422_0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODE = "TYPEFORM_PARIS_INITIATION_2025_2026_RICHELIEU"
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


def _school_year_label(connection: sa.Connection, row: dict[str, Any]) -> str:
    quote_type_id = row.get("default_quote_type_id")
    if quote_type_id is not None:
        label = connection.execute(
            sa.text(
                """
                SELECT school_year_label
                FROM quote_types
                WHERE id = :quote_type_id
                LIMIT 1
                """
            ),
            {"quote_type_id": quote_type_id},
        ).scalar()
        if isinstance(label, str) and label.strip():
            return label.strip()

    pricing_catalog_id = row.get("default_pricing_catalog_id")
    if pricing_catalog_id is not None:
        label = connection.execute(
            sa.text(
                """
                SELECT school_year_label
                FROM pricing_catalogs
                WHERE id = :pricing_catalog_id
                LIMIT 1
                """
            ),
            {"pricing_catalog_id": pricing_catalog_id},
        ).scalar()
        if isinstance(label, str) and label.strip():
            return label.strip()

    existing = row.get("school_year_label")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    return "2026-2027"


def upgrade() -> None:
    connection = op.get_bind()
    row = connection.execute(
        sa.text(
            """
            SELECT *
            FROM typeform_form_configs
            WHERE source_code = :source_code
            LIMIT 1
            """
        ),
        {"source_code": SOURCE_CODE},
    ).mappings().first()
    if row is None:
        return

    config_json = _json_object(row.get("configuration_json"))
    school_year_label = _school_year_label(connection, dict(row))
    config_json["label"] = f"Initiation {school_year_label}"
    config_json["line_templates"] = [
        {
            "kind": "activity",
            "activity_code": INITIATION_ACTIVITY_CODE,
            "quantity": "1",
        }
    ]

    connection.execute(
        sa.text(
            """
            UPDATE typeform_form_configs
            SET school_year_label = :school_year_label,
                configuration_json = CAST(:configuration_json AS jsonb),
                updated_at = now()
            WHERE id = :config_id
            """
        ),
        {
            "config_id": row["id"],
            "school_year_label": school_year_label,
            "configuration_json": json.dumps(config_json, ensure_ascii=True),
        },
    )


def downgrade() -> None:
    pass
