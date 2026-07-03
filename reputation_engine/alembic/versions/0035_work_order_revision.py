"""work_orders.added_in_revision: which plan revision first added a task

Plan regeneration is an ADDITIVE MERGE, not a replace: existing tasks (and their progress) are
kept, and only genuinely-new tasks from the regenerated plan are added -- tagged with the
revision number so the UI can mark them "Revision N · added". Revision 1 = the original plan.

Revision ID: 0035_work_order_revision
Revises: 0034_social_presence
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0035_work_order_revision"
down_revision = "0034_social_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS added_in_revision INT DEFAULT 1")


def downgrade() -> None:
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS added_in_revision")
