"""Add administrative task management.

Revision ID: 20260825_0208
Revises: 20260824_0207
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260825_0208"
down_revision = "20260824_0207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'CREATED'"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prospect_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("intake_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "task_type IN ('CLIENT_CALL','PROVIDER_CALL','SLOT_CHOICE','PROFESSOR_CONTACT','SHEET_MUSIC_DELIVERY')",
            name="ck_admin_tasks_type",
        ),
        sa.CheckConstraint(
            "status IN ('CREATED','ASSIGNED','IN_PROGRESS','COMPLETED','ARCHIVED')",
            name="ck_admin_tasks_status",
        ),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["intake_id"], ["typeform_intakes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_tasks_assignee_status", "admin_tasks", ["assignee_user_id", "status"])
    op.create_index("ix_admin_tasks_due_at", "admin_tasks", ["due_at"])
    op.create_index("ix_admin_tasks_client_id", "admin_tasks", ["client_id"])
    op.create_index("ix_admin_tasks_prospect_id", "admin_tasks", ["prospect_id"])
    op.create_index("ix_admin_tasks_intake_id", "admin_tasks", ["intake_id"])
    op.create_index("ix_admin_tasks_quote_id", "admin_tasks", ["quote_id"])


def downgrade() -> None:
    op.drop_index("ix_admin_tasks_quote_id", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_intake_id", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_prospect_id", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_client_id", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_due_at", table_name="admin_tasks")
    op.drop_index("ix_admin_tasks_assignee_status", table_name="admin_tasks")
    op.drop_table("admin_tasks")
