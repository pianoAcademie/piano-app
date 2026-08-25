"""Add administrative task comment history and waiting-client status.

Revision ID: 20260825_0209
Revises: 20260825_0208
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260825_0209"
down_revision = "20260825_0208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_admin_tasks_status", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_status",
        "admin_tasks",
        "status IN ('CREATED','ASSIGNED','IN_PROGRESS','WAITING_CLIENT','COMPLETED','ARCHIVED')",
    )
    op.create_table(
        "admin_task_comments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["admin_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_task_comments_task_created",
        "admin_task_comments",
        ["task_id", "created_at"],
    )
    op.create_index(
        "ix_admin_task_comments_author_user_id",
        "admin_task_comments",
        ["author_user_id"],
    )
    # L'ancien champ ne permet pas de savoir de façon fiable qui l'a modifié.
    # Il est néanmoins conservé dans l'historique avec sa dernière date connue.
    op.execute(
        """
        INSERT INTO admin_task_comments (task_id, author_user_id, body, created_at)
        SELECT id, NULL, btrim(comment), COALESCE(updated_at, created_at, now())
        FROM admin_tasks
        WHERE comment IS NOT NULL AND btrim(comment) <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_admin_task_comments_author_user_id", table_name="admin_task_comments")
    op.drop_index("ix_admin_task_comments_task_created", table_name="admin_task_comments")
    op.drop_table("admin_task_comments")
    op.drop_constraint("ck_admin_tasks_status", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_status",
        "admin_tasks",
        "status IN ('CREATED','ASSIGNED','IN_PROGRESS','COMPLETED','ARCHIVED')",
    )
