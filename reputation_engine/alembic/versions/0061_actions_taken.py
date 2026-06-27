"""actions_taken log + brief produced_on -- first-class completion/impact tracking (Phase A)

The feedback loop today only learns from ASSET rows (published content). A task an operator marks
done -- especially work done OUTSIDE the platform -- left no trace the learner could see. This adds:

- actions_taken: a first-class, task-type-aware log of work actually completed (with a real,
  back-datable completion date), decoupled from assets. This is the unit the feedback loop
  correlates to audit-over-audit "needle movement" so we can learn which task TYPES move the score.
- production_briefs.produced_on: lets content-to-produce be marked produced on a real date.

Revision ID: 0061_actions_taken
Revises: 0060_owned_domains
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0061_actions_taken"
down_revision = "0060_owned_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS actions_taken (
            id                  BIGSERIAL PRIMARY KEY,
            business_id         BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            work_order_id       BIGINT REFERENCES work_orders(id) ON DELETE SET NULL,
            production_brief_id BIGINT REFERENCES production_briefs(id) ON DELETE SET NULL,
            source              TEXT NOT NULL DEFAULT 'work_order',  -- work_order | brief | manual | asset
            capability          TEXT,            -- task type / capability (the feedback-loop learning key)
            area                TEXT,            -- website | blog | outreach | social | local | reviews
            platform            TEXT,            -- per-platform (linkedin, facebook, gbp, ...)
            title               TEXT,
            completed_on        DATE NOT NULL,   -- the REAL completion date (back-datable)
            logged_at           TIMESTAMPTZ DEFAULT now(),
            logged_by           TEXT,
            notes               TEXT,
            meta                JSONB DEFAULT '{}'::jsonb
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_actions_taken_biz ON actions_taken(business_id, completed_on DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_actions_taken_cap ON actions_taken(business_id, capability)")
    # One action row per work order (re-marking done updates the row, not duplicates it).
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_actions_wo ON actions_taken(work_order_id) "
               "WHERE work_order_id IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_actions_brief ON actions_taken(production_brief_id) "
               "WHERE production_brief_id IS NOT NULL")

    op.execute("ALTER TABLE production_briefs ADD COLUMN IF NOT EXISTS produced_on DATE")


def downgrade() -> None:
    op.execute("ALTER TABLE production_briefs DROP COLUMN IF EXISTS produced_on")
    op.execute("DROP TABLE IF EXISTS actions_taken")
