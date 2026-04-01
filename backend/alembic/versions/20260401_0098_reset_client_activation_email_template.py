"""reset client activation email template override to premium default

Revision ID: 20260401_0098
Revises: 20260401_0097
Create Date: 2026-04-01 16:20:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260401_0098"
down_revision: Union[str, None] = "20260401_0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
CLIENT_PASSWORD_TEMPLATE_CODE = "CLIENT_PASSWORD_SETUP"
LEGACY_CLIENT_PASSWORD_SUBJECT_KEY = "config_client_password_email_subject"
LEGACY_CLIENT_PASSWORD_BODY_KEY = "config_client_password_email_body"


def upgrade() -> None:
    connection = op.get_bind()

    raw_payload = connection.execute(
        sa.text("SELECT value FROM app_settings WHERE key = :key"),
        {"key": MESSAGING_PREDEFINED_TEMPLATES_KEY},
    ).scalar()
    if raw_payload:
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and CLIENT_PASSWORD_TEMPLATE_CODE in payload:
            payload.pop(CLIENT_PASSWORD_TEMPLATE_CODE, None)
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

    connection.execute(
        sa.text(
            """
            UPDATE app_settings
            SET value = '',
                updated_at = now()
            WHERE key = :key
            """
        ),
        {"key": LEGACY_CLIENT_PASSWORD_SUBJECT_KEY},
    )
    connection.execute(
        sa.text(
            """
            UPDATE app_settings
            SET value = '',
                updated_at = now()
            WHERE key = :key
            """
        ),
        {"key": LEGACY_CLIENT_PASSWORD_BODY_KEY},
    )


def downgrade() -> None:
    return None
