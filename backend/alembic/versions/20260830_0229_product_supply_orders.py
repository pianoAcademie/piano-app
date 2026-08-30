"""Track expected supplier deliveries separately from physical stock."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260830_0229"
down_revision = "20260830_0228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_supply_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reference", sa.String(255)),
        sa.Column("supplier", sa.String(255)),
        sa.Column("ordered_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ORDERED"),
        sa.Column("note", sa.Text()),
        sa.Column("received_date", sa.Date()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('ORDERED', 'RECEIVED', 'CANCELLED')", name="ck_supply_order_status"),
        sa.CheckConstraint("expected_delivery_date >= ordered_date", name="ck_supply_order_dates"),
    )
    op.create_index("ix_product_supply_orders_status", "product_supply_orders", ["status"])
    op.create_table(
        "product_supply_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_supply_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("catalog_products.id", ondelete="RESTRICT")),
        sa.Column("product_title", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stock_movement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stock_movements.id", ondelete="RESTRICT"), unique=True),
        sa.UniqueConstraint("order_id", "product_id", name="uq_supply_order_product"),
        sa.CheckConstraint("quantity > 0 AND quantity <= 1000000", name="ck_supply_order_quantity"),
    )
    op.create_index("ix_product_supply_order_lines_product_id", "product_supply_order_lines", ["product_id"])


def downgrade() -> None:
    op.drop_table("product_supply_order_lines")
    op.drop_table("product_supply_orders")
