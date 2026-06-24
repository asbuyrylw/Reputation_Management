"""work_orders.task_key (stable identity) + superseded (retirement)

- task_key: a stable identity for a task (capability + normalized title), set at creation, so the
  plan-merge matches tasks robustly even if a human renames the displayed title.
- superseded: when a regenerated plan no longer recommends a not-yet-started task, it's archived
  (superseded=TRUE, hidden by default) rather than left to pile up; it revives if a later plan
  recommends it again.

Revision ID: 0037_wo_taskkey_supersede
Revises: 0036_wo_assign_impact
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0037_wo_taskkey_supersede"
down_revision = "0036_wo_assign_impact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS task_key TEXT")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS superseded BOOLEAN DEFAULT FALSE")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_taskkey ON work_orders(business_id, task_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_work_orders_taskkey")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS task_key")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS superseded")
