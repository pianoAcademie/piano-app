"""fix Bar-le-Duc child Typeform document defaults

Revision ID: 20260615_0152
Revises: 20260615_0151
Create Date: 2026-06-15 17:05:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0152"
down_revision: Union[str, None] = "20260615_0151"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODE = "typeform_bld_child_2026_2027"

QUOTE_CODES = [
    "TEMPLATE_DEVIS_COLLECTIF_ENFANTS_BAR_LE_DUC",
    "TEMPLATE_DEVIS_COLLECTIF_ENFANTS_BAR_LE_DUC_EN",
    "TEMPLATE_BAR_LE_DUC_ENFANT",
    "TEMPLATE_BAR_LE_DUC_ENFANTS",
    "TEMPLATE_BLD_ENFANT",
    "TEMPLATE_BLD_ENFANTS",
    "TEMPLATE_COURS_COLLECTIF_ENFANT_BAR_LE_DUC",
    "TEMPLATE_COURS_COLLECTIF_ENFANT_BLD",
]

TERMS_CODES = [
    "COLLECTIF_ENFANTS_2025_2026_BAR_LE_DUC",
    "COLLECTIF_ENFANTS_2025_2026_BAR_LE_DUC_EN",
    "CGV_BAR_LE_DUC_ENFANTS_2026_2027",
    "CGV_BLD_ENFANTS_2026_2027",
    "CGV_ENFANTS_BAR_LE_DUC_2026_2027",
    "CGV_ENFANTS_BLD_2026_2027",
]


def _merge_codes(preferred: list[str], existing: object) -> list[str]:
    merged: list[str] = []
    for value in [*preferred, *(existing if isinstance(existing, list) else [])]:
        code = str(value or "").strip().upper()
        if code and code not in merged:
            merged.append(code)
    return merged


def _update_config(*, downgrade: bool = False) -> None:
    connection = op.get_bind()
    row = connection.execute(
        sa.text(
            """
            SELECT id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = :source_code
            LIMIT 1
            """
        ),
        {"source_code": SOURCE_CODE},
    ).mappings().first()
    if row is None:
        return

    config = dict(row["configuration_json"] or {})
    if downgrade:
        config["default_quote_template_codes"] = [
            code for code in config.get("default_quote_template_codes", []) if code not in QUOTE_CODES[:2]
        ]
        config["default_terms_template_codes"] = [
            code for code in config.get("default_terms_template_codes", []) if code not in TERMS_CODES[:2]
        ]
    else:
        config["default_quote_template_codes"] = _merge_codes(QUOTE_CODES, config.get("default_quote_template_codes"))
        config["default_terms_template_codes"] = _merge_codes(TERMS_CODES, config.get("default_terms_template_codes"))

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
    _update_config()


def downgrade() -> None:
    _update_config(downgrade=True)
