"""Add family links and adult/child client kind

Revision ID: 20260214_0015
Revises: 20260214_0014
Create Date: 2026-02-14 16:40:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260214_0015"
down_revision: Union[str, None] = "20260214_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    client_kind = postgresql.ENUM("ADULT", "CHILD", name="client_kind")
    client_kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "client_kind",
            postgresql.ENUM("ADULT", "CHILD", name="client_kind", create_type=False),
            nullable=False,
            server_default=sa.text("'ADULT'::client_kind"),
        ),
    )

    op.create_table(
        "client_family_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("adult_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_label", sa.String(length=80), nullable=True),
        sa.Column(
            "is_billing_recipient",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["adult_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("adult_user_id", "child_user_id", name="uq_client_family_links_pair"),
        sa.CheckConstraint("adult_user_id <> child_user_id", name="ck_client_family_links_not_self"),
    )
    op.create_index("ix_client_family_links_adult", "client_family_links", ["adult_user_id"], unique=False)
    op.create_index("ix_client_family_links_child", "client_family_links", ["child_user_id"], unique=False)
    op.create_index(
        "uq_client_family_links_child_billing_recipient",
        "client_family_links",
        ["child_user_id"],
        unique=True,
        postgresql_where=sa.text("is_billing_recipient"),
    )


def downgrade() -> None:
    op.drop_index("uq_client_family_links_child_billing_recipient", table_name="client_family_links")
    op.drop_index("ix_client_family_links_child", table_name="client_family_links")
    op.drop_index("ix_client_family_links_adult", table_name="client_family_links")
    op.drop_table("client_family_links")

    op.drop_column("users", "client_kind")

    client_kind = postgresql.ENUM("ADULT", "CHILD", name="client_kind")
    client_kind.drop(op.get_bind(), checkfirst=True)
