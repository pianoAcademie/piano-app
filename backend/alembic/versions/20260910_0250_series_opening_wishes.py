"""Allow annual transfer requests for a series that does not exist yet."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_0250"
down_revision = "20260910_0249"
branch_labels = None
depends_on = None

def upgrade():
    op.alter_column("annual_series_transfer_requests", "target_session_id", existing_type=postgresql.UUID(), nullable=True)
    op.alter_column("annual_series_transfer_requests", "target_recurrence_group_id", existing_type=postgresql.UUID(), nullable=True)
    op.add_column("annual_series_transfer_requests", sa.Column("desired_weekday", sa.Integer(), nullable=True))
    op.add_column("annual_series_transfer_requests", sa.Column("desired_time", sa.String(5), nullable=True))

def downgrade():
    # Unbound wishes must be attached or explicitly removed before downgrading.
    op.alter_column("annual_series_transfer_requests", "target_session_id", existing_type=postgresql.UUID(), nullable=False)
    op.alter_column("annual_series_transfer_requests", "target_recurrence_group_id", existing_type=postgresql.UUID(), nullable=False)
    op.drop_column("annual_series_transfer_requests", "desired_time")
    op.drop_column("annual_series_transfer_requests", "desired_weekday")
