"""Add client portal news articles.

Revision ID: 20260806_0183
Revises: 20260806_0182
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0183"
down_revision = "20260806_0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_news_articles",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title_fr", sa.String(length=220), nullable=False),
        sa.Column("title_en", sa.String(length=220), nullable=True),
        sa.Column("summary_fr", sa.String(length=500), nullable=True),
        sa.Column("summary_en", sa.String(length=500), nullable=True),
        sa.Column("body_fr", sa.Text(), nullable=False),
        sa.Column("body_en", sa.Text(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("link_label_fr", sa.String(length=120), nullable=True),
        sa.Column("link_label_en", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status in ('DRAFT', 'PUBLISHED')", name="ck_client_news_articles_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_client_news_articles_publication",
        "client_news_articles",
        ["status", "published_at", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_client_news_articles_publication", table_name="client_news_articles")
    op.drop_table("client_news_articles")
