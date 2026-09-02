"""Add dynamic audiences to client and professor news."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260901_0234"
down_revision = "20260901_0233"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "client_news_articles",
        sa.Column(
            "audience_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"ALL_CLIENTS\"]'::jsonb"),
        ),
    )
    op.execute("UPDATE client_news_articles SET audience_codes = '[\"ALL_CLIENTS\"]'::jsonb")


def downgrade():
    op.drop_column("client_news_articles", "audience_codes")
