"""notifications: in-app + email alerts (score drops, incidents, negative mentions, drafts)

The "managed service" needs to be PROACTIVE: tell the owner when something needs attention
instead of waiting for them to log in. check_and_notify() creates these; the API serves a
feed; email delivery is best-effort via email_service. dedup_key prevents re-alerting.

Revision ID: 0019_notifications
Revises: 0018_schedules
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0019_notifications"
down_revision = "0018_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            severity TEXT NOT NULL DEFAULT 'info',
            dedup_key TEXT,
            read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, dedup_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_biz ON notifications(business_id, read, id DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
