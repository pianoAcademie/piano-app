"""Add configurable family billing allocations.

Revision ID: 20260818_0203
Revises: 20260818_0202
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260818_0203"
down_revision = "20260818_0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_family_billing_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "child_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "payer_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("allocation_type", sa.String(length=20), nullable=False),
        sa.Column("allocation_value", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "allocation_type IN ('PERCENT', 'FIXED', 'REMAINDER')",
            name="ck_client_family_billing_allocation_type",
        ),
        sa.CheckConstraint(
            "(allocation_type = 'REMAINDER' AND allocation_value IS NULL) OR "
            "(allocation_type <> 'REMAINDER' AND allocation_value IS NOT NULL AND allocation_value >= 0)",
            name="ck_client_family_billing_allocation_value",
        ),
        sa.UniqueConstraint(
            "child_user_id",
            "payer_user_id",
            name="uq_client_family_billing_allocation_child_payer",
        ),
    )
    op.create_index(
        "ix_client_family_billing_allocations_child",
        "client_family_billing_allocations",
        ["child_user_id"],
    )
    op.create_index(
        "ix_client_family_billing_allocations_payer",
        "client_family_billing_allocations",
        ["payer_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_client_family_billing_allocations_payer",
        table_name="client_family_billing_allocations",
    )
    op.drop_index(
        "ix_client_family_billing_allocations_child",
        table_name="client_family_billing_allocations",
    )
    op.drop_table("client_family_billing_allocations")
