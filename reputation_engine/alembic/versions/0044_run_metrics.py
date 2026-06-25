"""run_metrics — per-audit-run metric rollup (so per-prompt/per-engine TRENDS survive answer pruning)

per_prompt_metrics/per_engine_metrics only ever computed the LATEST run, so the console could
show "Claude scores 62 today" but never "this engine went 40->68 over 3 audits". This persists a
small rollup per run (overall + per-engine), captured at run-complete, so the trend is durable.

Revision ID: 0044_run_metrics
Revises: 0043_regulatory_profile
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0044_run_metrics"
down_revision = "0043_regulatory_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS run_metrics (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        run_id BIGINT UNIQUE,
        goal_alignment NUMERIC,
        contested_rate NUMERIC,
        owned_rate NUMERIC,
        grounded_rate NUMERIC,
        metrics JSONB DEFAULT '{}'::jsonb,
        captured_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_run_metrics_biz ON run_metrics(business_id, run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS run_metrics")
