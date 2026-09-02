"""student sheet-music repertoire and piece library

Revision ID: 20260902_0236
Revises: 20260902_0235
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260902_0236"
down_revision = "20260902_0235"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sheet_music_pieces",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("catalog_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("video_url", sa.Text()), sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("product_id", "position", name="uq_sheet_music_piece_position"))
    op.create_index("ix_sheet_music_pieces_product_id", "sheet_music_pieces", ["product_id"])
    op.create_table("student_sheet_music",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("catalog_products.id", ondelete="SET NULL")),
        sa.Column("title_snapshot", sa.String(255), nullable=False), sa.Column("status", sa.String(20), server_default="STANDBY", nullable=False),
        sa.Column("current_piece_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sheet_music_pieces.id", ondelete="SET NULL")),
        sa.Column("source_quote_line_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quote_lines.id", ondelete="SET NULL")),
        sa.Column("internal_note", sa.Text()), sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('STANDBY','TO_DELIVER','DELIVERED','IN_PROGRESS','COMPLETED')", name="ck_student_sheet_music_status"),
        sa.UniqueConstraint("source_quote_line_id", name="uq_student_sheet_music_source_quote_line"))
    op.create_index("ix_student_sheet_music_student_id", "student_sheet_music", ["student_id"])
    op.create_index("ix_student_sheet_music_product_id", "student_sheet_music", ["product_id"])
    op.create_index("ix_student_sheet_music_status", "student_sheet_music", ["status"])
    op.create_table("student_sheet_music_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("student_sheet_music.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("old_status", sa.String(20)), sa.Column("new_status", sa.String(20)),
        sa.Column("piece_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sheet_music_pieces.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("ix_student_sheet_music_events_assignment_id", "student_sheet_music_events", ["assignment_id"])


def downgrade():
    op.drop_table("student_sheet_music_events")
    op.drop_table("student_sheet_music")
    op.drop_table("sheet_music_pieces")
