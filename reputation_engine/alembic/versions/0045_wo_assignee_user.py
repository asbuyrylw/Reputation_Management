"""work_orders.assignee_user_id — FK-backed assignees (so 'Alice'/'Alice Chen'/'AC' stop fragmenting)

`assignee` was unvalidated free text, so the by-assignee board view was noise and workload couldn't
be measured. This adds a real user FK; the display `assignee` is kept (set from the user's name) for
backward-compatible rendering.

Revision ID: 0045_wo_assignee_user
Revises: 0044_run_metrics
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0045_wo_assignee_user"
down_revision = "0044_run_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS assignee_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_assignee_user ON work_orders(business_id, assignee_user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_work_orders_assignee_user")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS assignee_user_id")
