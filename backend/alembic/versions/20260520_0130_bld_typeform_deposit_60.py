"""set Bar-le-Duc Typeform deposit to 60 euros

Revision ID: 20260520_0130
Revises: 20260519_0129
Create Date: 2026-05-20 09:00:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0130"
down_revision: Union[str, None] = "20260519_0129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODES = (
    "typeform_bld_child_2026_2027",
    "typeform_bld_adult_2026_2027",
)


def _set_deposit_amount(amount_ttc: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, configuration_json
            FROM typeform_form_configs
            WHERE source_code = ANY(:source_codes)
            """
        ),
        {"source_codes": list(SOURCE_CODES)},
    ).mappings().all()

    for row in rows:
        config = dict(row["configuration_json"] or {})
        changed = False
        if config.get("default_pre_registration_deposit_enabled") is not True:
            config["default_pre_registration_deposit_enabled"] = True
            changed = True
        if config.get("default_pre_registration_deposit_amount_ttc") != amount_ttc:
            config["default_pre_registration_deposit_amount_ttc"] = amount_ttc
            changed = True
        if not changed:
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
            {"id": row["id"], "configuration_json": json.dumps(config, ensure_ascii=True)},
        )


def upgrade() -> None:
    _set_deposit_amount("60.00")


def downgrade() -> None:
    _set_deposit_amount("200.00")
