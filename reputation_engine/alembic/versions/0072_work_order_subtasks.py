"""work_orders.subtasks: a per-step checklist on a task

A task with a multi-step instruction can now track each step's done state individually (the owner
checks them off). Stored as a JSONB array of {text, done}. Guaranteed on deploy so the work-orders
read (which now selects subtasks) can't hit a missing column.

Revision ID: 0072_work_order_subtasks
Revises: 0071_content_batches_impact
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op

revision = "0072_work_order_subtasks"
down_revision = "0071_content_batches_impact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS subtasks JSONB DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS subtasks")
