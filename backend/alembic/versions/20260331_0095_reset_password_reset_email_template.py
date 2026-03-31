"""reset password reset email template override to new premium default

Revision ID: 20260331_0095
Revises: 20260331_0094
Create Date: 2026-03-31 12:05:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260331_0095"
down_revision: Union[str, None] = "20260331_0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
PASSWORD_RESET_TEMPLATE_CODE = "PASSWORD_RESET"


def upgrade() -> None:
    connection = op.get_bind()
    raw_payload = connection.execute(
        sa.text("SELECT value FROM app_settings WHERE key = :key"),
        {"key": MESSAGING_PREDEFINED_TEMPLATES_KEY},
    ).scalar()
    if not raw_payload:
        return
    try:
        payload = json.loads(str(raw_payload))
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    if PASSWORD_RESET_TEMPLATE_CODE not in payload:
        return

    payload.pop(PASSWORD_RESET_TEMPLATE_CODE, None)
    connection.execute(
        sa.text(
            """
            UPDATE app_settings
            SET value = :value,
                updated_at = now()
            WHERE key = :key
            """
        ),
        {
            "key": MESSAGING_PREDEFINED_TEMPLATES_KEY,
            "value": json.dumps(payload, ensure_ascii=True),
        },
    )


def downgrade() -> None:
    return None
