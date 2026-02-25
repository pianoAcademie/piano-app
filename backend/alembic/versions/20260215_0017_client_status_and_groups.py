"""add client status lifecycle and client groups

Revision ID: 20260215_0017
Revises: 20260214_0016
Create Date: 2026-02-15 17:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260215_0017"
down_revision: Union[str, None] = "20260214_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_GROUPS = [
    ("EVEIL_MUSICAL", "Eveil musical"),
    ("INITIATION", "Initiation"),
    ("COLLECTIF_ENFANT", "Collectif enfant"),
    ("COLLECTIF_ADO", "Collectif ado"),
    ("COLLECTIF_ADULTE", "Collectif adulte"),
    ("ADULTE_EN_LIGNE", "Adulte en ligne"),
    ("ENFANT_EN_LIGNE", "Enfant en ligne"),
]


def upgrade() -> None:
    client_status = postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        "TRIAL",
        "PENDING",
        "ARCHIVED",
        name="client_status",
    )
    client_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column(
            "client_status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "TRIAL",
                "PENDING",
                "ARCHIVED",
                name="client_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'ACTIVE'::client_status"),
        ),
    )
    op.create_index("ix_users_client_status", "users", ["client_status"], unique=False)

    op.execute(
        """
        UPDATE users
        SET client_status = CASE
            WHEN is_active THEN 'ACTIVE'::client_status
            ELSE 'INACTIVE'::client_status
        END
        WHERE role = 'client'::user_role
        """
    )

    op.create_table(
        "client_groups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint("code", name="uq_client_groups_code"),
        sa.UniqueConstraint("name", name="uq_client_groups_name"),
    )

    op.create_table(
        "client_group_memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["client_groups.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "group_id", name="uq_client_group_memberships_user_group"),
    )
    op.create_index("ix_client_group_memberships_user_id", "client_group_memberships", ["user_id"], unique=False)
    op.create_index("ix_client_group_memberships_group_id", "client_group_memberships", ["group_id"], unique=False)

    for code, name in DEFAULT_GROUPS:
        op.execute(
            sa.text(
                """
                INSERT INTO client_groups (code, name, active)
                VALUES (:code, :name, true)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, name=name)
        )


def downgrade() -> None:
    op.drop_index("ix_client_group_memberships_group_id", table_name="client_group_memberships")
    op.drop_index("ix_client_group_memberships_user_id", table_name="client_group_memberships")
    op.drop_table("client_group_memberships")
    op.drop_table("client_groups")

    op.drop_index("ix_users_client_status", table_name="users")
    op.drop_column("users", "client_status")

    client_status = postgresql.ENUM(
        "ACTIVE",
        "INACTIVE",
        "TRIAL",
        "PENDING",
        "ARCHIVED",
        name="client_status",
    )
    client_status.drop(op.get_bind(), checkfirst=True)
