"""notifications.user_id -- user-targeted alerts (Rec #7)

Notifications were business-scoped (everyone on the business saw the same feed). Adding an optional
user_id lets a notification target a SPECIFIC user -- e.g. "you were assigned a task" -- while a NULL
user_id stays business-wide (audits, incidents, score drops). A NULL user_id therefore reads as
"everyone on the business".

Revision ID: 0066_notif_user
Revises: 0065_narrative_scores
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0066_notif_user"
down_revision = "0065_narrative_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id BIGINT "
               "REFERENCES users(id) ON DELETE CASCADE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read, id DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notifications_user")
    op.execute("ALTER TABLE notifications DROP COLUMN IF EXISTS user_id")
