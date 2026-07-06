"""Retire the manual-promote gate: gap/strategy-generated tasks land on the board directly

Product reversal of migration 0038 (which added a "promote a recommendation onto the managed
board" step, `planned` default FALSE). The owner now wants every gap-derived task to already be
a real, trackable task the moment the strategy runs -- no separate "Recommendations" pile
requiring a manual promote click. Manual "+ Add as task" additions already set planned=TRUE
(tracking.create_work_order); `tracking.sync_plan` is updated alongside this migration to do the
same for plan-generated rows. This migration (a) flips the column default so any future insert
path that omits the field lands on the board rather than in limbo, and (b) backfills every
currently-open, not-yet-promoted recommendation so existing data reflects the same decision
immediately, not just future audits.

Revision ID: 0075_tasks_from_gaps_no_gate
Revises: 0074_citation_runs
Create Date: 2026-07-06
"""
from __future__ import annotations

from alembic import op

revision = "0075_tasks_from_gaps_no_gate"
down_revision = "0074_citation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ALTER COLUMN planned SET DEFAULT TRUE")
    op.execute(
        "UPDATE work_orders SET planned=TRUE, updated_at=now() "
        "WHERE planned=FALSE AND NOT COALESCE(superseded, false) "
        "AND status NOT IN ('done', 'verified', 'skipped')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE work_orders ALTER COLUMN planned SET DEFAULT FALSE")
    # Data backfill is not reversible (we can't tell which rows were promoted before vs. by this
    # migration) -- downgrade only reverts the column default, matching how 0038 itself behaved.
