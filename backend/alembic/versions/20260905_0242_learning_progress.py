"""Track learning independently from the physical distribution of books."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260905_0242"
down_revision = "20260905_0241"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("student_learning_progress",
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", JSONB, nullable=False))
    op.create_table("student_learning_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("course_sessions.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("before_state", JSONB, nullable=False),
        sa.Column("after_state", JSONB, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
    op.create_index("ix_student_learning_events_student_id", "student_learning_events", ["student_id"])


def downgrade():
    op.drop_table("student_learning_events")
    op.drop_table("student_learning_progress")
