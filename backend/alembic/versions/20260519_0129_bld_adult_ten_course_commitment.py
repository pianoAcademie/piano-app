"""limit Bar-le-Duc adult ten-course commitments

Revision ID: 20260519_0129
Revises: 20260519_0128
Create Date: 2026-05-19 21:20:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0129"
down_revision: Union[str, None] = "20260519_0128"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODE = "typeform_bld_adult_2026_2027"
TEN_COURSE_PRODUCTS = {
    "Engagement sur 10 cours - 26€ / cours",
    "Engagement 10 cours - 45€/h",
}


def _requested_products(template: dict[str, object]) -> set[str]:
    when = template.get("when")
    if not isinstance(when, dict):
        return set()
    products = when.get("requested_products")
    if not isinstance(products, list):
        return set()
    return {str(item or "").strip() for item in products if str(item or "").strip()}


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
    line_templates = list(config.get("line_templates") or [])
    changed = False
    for template in line_templates:
        if not isinstance(template, dict):
            continue
        if not (_requested_products(template) & TEN_COURSE_PRODUCTS):
            continue
        if downgrade:
            if template.get("quantity") != "1":
                template["quantity"] = "1"
                changed = True
            for key in ("commitment_kind", "planning_session_limit"):
                if key in template:
                    template.pop(key, None)
                    changed = True
        else:
            if template.get("quantity") != "10":
                template["quantity"] = "10"
                changed = True
            if template.get("commitment_kind") != "ten_course_pack":
                template["commitment_kind"] = "ten_course_pack"
                changed = True
            if template.get("planning_session_limit") != 10:
                template["planning_session_limit"] = 10
                changed = True

    if not changed:
        return

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
        {"id": row["id"], "configuration_json": json.dumps(config, ensure_ascii=True)},
    )


def upgrade() -> None:
    _update_config()


def downgrade() -> None:
    _update_config(downgrade=True)
