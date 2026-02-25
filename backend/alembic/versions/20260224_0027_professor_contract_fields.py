"""add professor contract storage columns

Revision ID: 20260224_0027
Revises: 20260223_0026
Create Date: 2026-02-24 10:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260224_0027"
down_revision: Union[str, None] = "20260223_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _professors_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("professors")}


def upgrade() -> None:
    existing = _professors_columns()
    if "contract_file_name" not in existing:
        op.add_column("professors", sa.Column("contract_file_name", sa.String(length=255), nullable=True))
    if "contract_content_type" not in existing:
        op.add_column("professors", sa.Column("contract_content_type", sa.String(length=100), nullable=True))
    if "contract_file_data" not in existing:
        op.add_column("professors", sa.Column("contract_file_data", sa.LargeBinary(), nullable=True))
    if "contract_uploaded_at" not in existing:
        op.add_column("professors", sa.Column("contract_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    existing = _professors_columns()
    if "contract_uploaded_at" in existing:
        op.drop_column("professors", "contract_uploaded_at")
    if "contract_file_data" in existing:
        op.drop_column("professors", "contract_file_data")
    if "contract_content_type" in existing:
        op.drop_column("professors", "contract_content_type")
    if "contract_file_name" in existing:
        op.drop_column("professors", "contract_file_name")
