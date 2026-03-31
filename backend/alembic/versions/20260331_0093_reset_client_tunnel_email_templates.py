"""reset client tunnel email template overrides to harmonized defaults

Revision ID: 20260331_0093
Revises: 20260330_0092
Create Date: 2026-03-31 08:00:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260331_0093"
down_revision: Union[str, None] = "20260330_0092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
HARMONIZED_CLIENT_TEMPLATE_CODES = (
    "CLIENT_BOOKING_CONFIRMATION",
    "INVOICE",
    "INVOICE_PAID",
    "INVOICE_REMINDER",
    "PAYMENT",
    "PAYMENT_CONFIRMED",
    "PAYMENT_RECEIPT",
)


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

    changed = False
    for template_code in HARMONIZED_CLIENT_TEMPLATE_CODES:
        if template_code in payload:
            payload.pop(template_code, None)
            changed = True

    if not changed:
        return

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
    # Irreversible: previous overrides are intentionally discarded so code defaults apply again.
    return None
