"""fix Typeform payment method mapping for Paris child form

Revision ID: 20260512_0113
Revises: 20260512_0112
Create Date: 2026-05-12 14:45:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260512_0113"
down_revision: Union[str, None] = "20260512_0112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODE = "typeform_paris_child_2026_2027_multisite"
FORM_ID = "G8eqpU6H"
PAYMENT_FIELD_REFS = [
    "f152efb5-e514-4942-98b5-3b015ffe5e93",
    "WXPcjzBDDPTz",
    "Mode de règlement souhaité pour l'année à venir",
    "Mode de reglement souhaite pour l'annee a venir",
]


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = :source_code
               OR typeform_form_id = :form_id
            """
        ),
        {"source_code": SOURCE_CODE, "form_id": FORM_ID},
    ).mappings().all()
    for row in rows:
        config_json = dict(row["configuration_json"] or {})
        field_mapping = dict(config_json.get("field_mapping") or {})
        existing = list(field_mapping.get("requested_payment_method") or [])
        for ref in PAYMENT_FIELD_REFS:
            if ref not in existing:
                existing.append(ref)
        field_mapping["requested_payment_method"] = existing
        config_json["field_mapping"] = field_mapping
        connection.execute(
            sa.text(
                """
                UPDATE typeform_form_configs
                SET configuration_json = CAST(:configuration_json AS jsonb),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": row["id"], "configuration_json": json.dumps(config_json)},
        )


def downgrade() -> None:
    return None
