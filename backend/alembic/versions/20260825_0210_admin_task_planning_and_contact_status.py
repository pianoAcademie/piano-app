"""Add planning task type and contacted-without-response status.

Revision ID: 20260825_0210
Revises: 20260825_0209
"""

from alembic import op


revision = "20260825_0210"
down_revision = "20260825_0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_admin_tasks_type", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_type",
        "admin_tasks",
        "task_type IN ('CLIENT_CALL','PROVIDER_CALL','SLOT_CHOICE','PROFESSOR_CONTACT','SHEET_MUSIC_DELIVERY','PLANNING')",
    )
    op.drop_constraint("ck_admin_tasks_status", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_status",
        "admin_tasks",
        "status IN ('CREATED','ASSIGNED','IN_PROGRESS','CONTACTED_NO_RESPONSE','WAITING_CLIENT','COMPLETED','ARCHIVED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_admin_tasks_status", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_status",
        "admin_tasks",
        "status IN ('CREATED','ASSIGNED','IN_PROGRESS','WAITING_CLIENT','COMPLETED','ARCHIVED')",
    )
    op.drop_constraint("ck_admin_tasks_type", "admin_tasks", type_="check")
    op.create_check_constraint(
        "ck_admin_tasks_type",
        "admin_tasks",
        "task_type IN ('CLIENT_CALL','PROVIDER_CALL','SLOT_CHOICE','PROFESSOR_CONTACT','SHEET_MUSIC_DELIVERY')",
    )
