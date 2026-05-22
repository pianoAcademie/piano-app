"""configure card 4x Oney quote PDF wording

Revision ID: 20260522_0132
Revises: 20260520_0131
Create Date: 2026-05-22 07:15:00.000000
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260522_0132"
down_revision: Union[str, None] = "20260520_0131"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ONEY_PAYMENT_INSTRUCTION = (
    "Le paiement par carte bancaire en 4 fois est géré par notre partenaire Oney.\n"
    "Votre dossier sera donc soumis à Oney, qui pourra l’accepter ou le refuser.\n"
    "Une partie des frais liés au paiement échelonné est prise en charge par Piano Académie. "
    "L’autre partie sera directement intégrée à votre échéancier par Oney."
)


def _rules_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, schedule_rules
            FROM payment_plans
            WHERE upper(payment_method) = 'CARD_4X_FEES'
            """
        )
    ).mappings()
    for row in rows:
        rules = _rules_object(row["schedule_rules"])
        visibility = _rules_object(rules.get("schedule_visibility"))
        visibility["client_pdf"] = False
        visibility.setdefault("admin_preview", True)
        visibility.setdefault("public_page", False)
        rules["schedule_visibility"] = visibility
        if not str(rules.get("payment_instruction") or "").strip():
            rules["payment_instruction"] = ONEY_PAYMENT_INSTRUCTION
        connection.execute(
            sa.text(
                """
                UPDATE payment_plans
                SET schedule_rules = CAST(:rules AS jsonb),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": row["id"], "rules": json.dumps(rules, ensure_ascii=False)},
        )


def downgrade() -> None:
    pass
