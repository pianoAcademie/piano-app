"""Set the default quote expiry to three days and the reminder to J-1.

Revision ID: 20260903_0239
Revises: 20260903_0238
"""

from alembic import op


revision = "20260903_0239"
down_revision = "20260903_0238"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("quote_types", "default_expiry_days", server_default="3")
    op.alter_column("quotes", "expiry_days", server_default="3")
    op.execute("update quote_types set default_expiry_days = 3, updated_at = now()")
    op.execute(
        """
        update quotes
        set expiry_days = 3,
            expires_at = null,
            updated_at = now()
        where sent_at is null
          and status = 'created'
          and expiry_days in (5, 7, 10)
        """
    )
    op.execute(
        """
        insert into app_settings (key, value, updated_at)
        values ('config_messaging_quote_reminder_lead_hours_csv', '24', now())
        on conflict (key) do update
        set value = excluded.value,
            updated_at = excluded.updated_at
        """
    )


def downgrade() -> None:
    op.alter_column("quote_types", "default_expiry_days", server_default="10")
    op.alter_column("quotes", "expiry_days", server_default="10")
    op.execute("update quote_types set default_expiry_days = 10, updated_at = now()")
    op.execute(
        """
        update app_settings
        set value = '72,24',
            updated_at = now()
        where key = 'config_messaging_quote_reminder_lead_hours_csv'
        """
    )
