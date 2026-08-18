"""Link product requests to delivery sessions and physical stock readiness.

Revision ID: 20260818_0202
Revises: 20260815_0201
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260818_0202"
down_revision = "20260815_0201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE product_request_status ADD VALUE IF NOT EXISTS 'WAITING_STOCK' BEFORE 'INVOICE_TO_SEND'")

    op.add_column(
        "product_requests",
        sa.Column(
            "assigned_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("course_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "product_requests",
        sa.Column(
            "assigned_professor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("professors.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "product_requests",
        sa.Column(
            "stock_transfer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_stock_transfers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "product_requests",
        sa.Column("stock_reserved_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("product_requests", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("product_requests", sa.Column("professor_notified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        "ck_product_requests_stock_reserved_non_negative",
        "product_requests",
        "stock_reserved_quantity >= 0",
    )
    op.create_index("ix_product_requests_assigned_session", "product_requests", ["assigned_session_id", "status"])
    op.create_index("ix_product_requests_assigned_professor", "product_requests", ["assigned_professor_id", "status"])
    op.create_index("ix_product_requests_stock_transfer", "product_requests", ["stock_transfer_id"])


def downgrade() -> None:
    op.drop_index("ix_product_requests_stock_transfer", table_name="product_requests")
    op.drop_index("ix_product_requests_assigned_professor", table_name="product_requests")
    op.drop_index("ix_product_requests_assigned_session", table_name="product_requests")
    op.drop_constraint("ck_product_requests_stock_reserved_non_negative", "product_requests", type_="check")
    op.drop_column("product_requests", "professor_notified_at")
    op.drop_column("product_requests", "ready_at")
    op.drop_column("product_requests", "stock_reserved_quantity")
    op.drop_column("product_requests", "stock_transfer_id")
    op.drop_column("product_requests", "assigned_professor_id")
    op.drop_column("product_requests", "assigned_session_id")
    # PostgreSQL enum values are intentionally retained on downgrade. Removing one
    # safely requires rebuilding the type and every dependent column.
