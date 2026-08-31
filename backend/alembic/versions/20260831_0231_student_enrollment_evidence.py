"""Store administrative renewal evidence without repricing existing documents."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260831_0231"
down_revision = "20260830_0230"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("annual_student_enrollments",
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("season", sa.String(9), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False))


def downgrade():
    op.drop_table("annual_student_enrollments")
