"""local_seo_goals: a first-class "get to page 1 of Google" goal + projection

Mirrors the AI-reputation timeline for local search. local_seo_goals.estimate() reads the
local_rankings history and writes one row per run: current page-one rate, the target, and an
optimistic/expected/conservative projection + confidence -- so local SEO gets its own goal,
timeline, and dashboard widget alongside the AI-reputation score.

Revision ID: 0032_local_seo_goals
Revises: 0031_discovery_enrich
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0032_local_seo_goals"
down_revision = "0031_discovery_enrich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS local_seo_goals (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            run_id BIGINT,
            goal JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_seo_goals_biz "
        "ON local_seo_goals(business_id, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS local_seo_goals")
