"""work_orders promotion workflow: planned flag + promotion metadata + progress notes

Separates RECOMMENDATIONS (Do-this-next) from MANAGED tasks (Improvement tasks):
- planned: TRUE once a recommendation has been promoted into the managed board (or for
  manually-created tasks, which are managed by definition). Plan-synced rows default FALSE.
- promoted_at / promoted_by: when and by whom it was promoted.
- progress_notes: an append-only JSONB log of {text, author, at} entries.

Per the owner's decision, ALL existing tasks are treated as fresh recommendations, so the
managed board starts empty (planned=FALSE) and fills as the owner promotes items.

Revision ID: 0038_wo_planned_promote
Revises: 0037_wo_taskkey_supersede
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0038_wo_planned_promote"
down_revision = "0037_wo_taskkey_supersede"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS planned BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS promoted_by TEXT")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS progress_notes JSONB DEFAULT '[]'::jsonb")
    # All current tasks become fresh recommendations; the managed board starts empty.
    op.execute("UPDATE work_orders SET planned=FALSE WHERE planned IS NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS progress_notes")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS promoted_by")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS promoted_at")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS planned")
