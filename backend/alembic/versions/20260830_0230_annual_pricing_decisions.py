"""Persist annual family references and contractual course decisions (no historical repricing)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260830_0230"
down_revision = "20260830_0229"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "annual_family_references",
        sa.Column("guardian_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("season", sa.String(9), primary_key=True),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("client_plan_subscriptions", sa.Column("annual_pricing_terms", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    op.drop_column("client_plan_subscriptions", "annual_pricing_terms")
    op.drop_table("annual_family_references")
