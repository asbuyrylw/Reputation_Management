"""external_signals: ingested 3rd-party SEO/SERP/keyword/backlink/visitor reports

v1 upload/paste + LLM-assisted normalization. Raw content is stored immediately (no
LLM); a background job fills `normalized` via the budget-gated agent_tools seam
(fenced as untrusted). See rep_engine.external_signals.

Revision ID: 0009_external_signals
Revises: 0008_api_jobs
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op

revision = "0009_external_signals"
down_revision = "0008_api_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS external_signals (
            id          BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            source      TEXT,                 -- siteguru | screpy | clickrank | ...
            signal_type TEXT,                 -- technical_seo|keywords|serp_rank|backlinks|brand|visitors|other
            raw         JSONB,                -- the uploaded/pasted report
            normalized  JSONB,                -- LLM-extracted structured facts (filled by the job)
            status      TEXT DEFAULT 'raw',   -- raw | normalized | failed
            captured_at TIMESTAMPTZ DEFAULT now(),
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_extsig_biz ON external_signals(business_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS external_signals CASCADE")
