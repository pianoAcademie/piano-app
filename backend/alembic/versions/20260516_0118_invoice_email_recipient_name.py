"""use full recipient name in invoice email greetings

Revision ID: 20260516_0118
Revises: 20260516_0117
Create Date: 2026-05-16 16:35:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0118"
down_revision: Union[str, None] = "20260516_0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MESSAGING_PREDEFINED_TEMPLATES_KEY = "config_messaging_predefined_templates_v1"
INVOICE_TEMPLATE_CODES = ("INVOICE", "INVOICE_PAID", "INVOICE_REMINDER")


def _replace_first_name_placeholder(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.replace("{first_name}", "{recipient_name}")


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
    for template_code in INVOICE_TEMPLATE_CODES:
        override = payload.get(template_code)
        if not isinstance(override, dict):
            continue
        for key in ("body", "subject"):
            current = override.get(key)
            updated = _replace_first_name_placeholder(current)
            if updated != current:
                override[key] = updated
                changed = True
        translations = override.get("body_translations")
        if isinstance(translations, dict):
            for language, current in list(translations.items()):
                updated = _replace_first_name_placeholder(current)
                if updated != current:
                    translations[language] = updated
                    changed = True
        subject_translations = override.get("subject_translations")
        if isinstance(subject_translations, dict):
            for language, current in list(subject_translations.items()):
                updated = _replace_first_name_placeholder(current)
                if updated != current:
                    subject_translations[language] = updated
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
    return None
