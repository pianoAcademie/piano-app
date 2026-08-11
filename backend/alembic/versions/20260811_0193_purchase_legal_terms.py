"""store purchase legal terms acceptance

Revision ID: 20260811_0193
Revises: 20260809_0192
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0193"
down_revision = "20260809_0192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_language", sa.String(length=8), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_version", sa.String(length=80), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_content_hash", sa.String(length=64), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_content_snapshot", sa.Text(), nullable=True))
    op.add_column("client_plan_subscriptions", sa.Column("legal_terms_acceptance_ip", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("client_plan_subscriptions", "legal_terms_acceptance_ip")
    op.drop_column("client_plan_subscriptions", "legal_terms_content_snapshot")
    op.drop_column("client_plan_subscriptions", "legal_terms_content_hash")
    op.drop_column("client_plan_subscriptions", "legal_terms_version")
    op.drop_column("client_plan_subscriptions", "legal_terms_language")
    op.drop_column("client_plan_subscriptions", "legal_terms_accepted_at")
