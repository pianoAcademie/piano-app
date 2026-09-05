"""Track physical partitions held by professors separately from student progress."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260905_0241"
down_revision = "20260904_0240"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "partition_movements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("operation_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("professor_id", UUID(as_uuid=True), sa.ForeignKey("professors.id"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("catalog_products.id"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("assignment_id", UUID(as_uuid=True), sa.ForeignKey("student_sheet_music.id"), unique=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("confirmed_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("quantity > 0", name="ck_partition_movement_quantity"),
        sa.CheckConstraint("kind IN ('PICKUP','RETURN','DELIVERY')", name="ck_partition_movement_kind"),
        sa.CheckConstraint("state IN ('PENDING','CONFIRMED','CANCELLED')", name="ck_partition_movement_state"),
    )
    op.create_index("ix_partition_movements_professor_id", "partition_movements", ["professor_id"])
    op.create_index("ix_partition_movements_product_id", "partition_movements", ["product_id"])


def downgrade():
    op.drop_table("partition_movements")
