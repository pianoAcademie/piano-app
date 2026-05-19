"""fix Bar-le-Duc child course mode matching

Revision ID: 20260519_0128
Revises: 20260519_0127
Create Date: 2026-05-19 20:15:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0128"
down_revision: Union[str, None] = "20260519_0127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_CODE = "typeform_bld_child_2026_2027"
COLLECTIVE_VALUES = [
    "Cours collectif",
    "Cours collectif de 1h",
    "Cours collectif de 1h (22€/h)",
    "Cours collectif de 1h  (22€/h)",
]
PRIVATE_VALUES = [
    "Cours particulier",
    "Cours particulier de 1h",
    "Cours particulier de 1h (40€/h)",
]


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
    for template in line_templates:
        if not isinstance(template, dict):
            continue
        when = template.setdefault("when", {})
        if not isinstance(when, dict):
            when = {}
            template["when"] = when
        activity_code = template.get("activity_code")
        if activity_code == "PIANO_GROUP_ONSITE_1H":
            when["requested_course_mode"] = ["Cours collectif"] if downgrade else COLLECTIVE_VALUES
        elif activity_code == "ACT_COURS_PARTICULIER_5DFFD9":
            when["requested_course_mode"] = ["Cours particulier"] if downgrade else PRIVATE_VALUES

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
