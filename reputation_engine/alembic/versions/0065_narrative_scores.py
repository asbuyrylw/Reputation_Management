"""narrative_scores -- the headline Narrative Crowding-Out Score per run (Rec #1a)

A single, client-legible 0-100 metric: how much the DESIRED narrative dominates AI answers vs the
CONTESTED one. Persisted per run so the trend survives answer pruning (answers are large and get
trimmed; this rollup is tiny and permanent), the same durability pattern as run_metrics.

Revision ID: 0065_narrative_scores
Revises: 0064_serper_cache
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0065_narrative_scores"
down_revision = "0064_serper_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS narrative_scores (
            business_id   BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            run_id        BIGINT NOT NULL,
            score         NUMERIC(5,1),    -- 0-100: desired-narrative dominance
            desired_pct   NUMERIC(5,1),
            contested_pct NUMERIC(5,1),
            neutral_pct   NUMERIC(5,1),
            n_answers     INT,
            by_engine     JSONB DEFAULT '{}'::jsonb,
            computed_at   TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (business_id, run_id)
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS narrative_scores")
