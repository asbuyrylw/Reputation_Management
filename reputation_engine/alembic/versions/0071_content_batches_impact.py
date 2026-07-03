"""content batches + measured impact + richer draft typing

The content program moves from one-piece-at-a-time to GAP-DRIVEN BATCHES: for a single gap we
generate MULTIPLE content types (blog, article, white paper, social, landing/local page), then
measure each type's — and the batch's collective — effect on the AI-visibility / SEO gap it was
built to close.

- content_batches: one row per (gap -> a set of pieces). Carries the target prompt cluster and a
  baseline SoV/alignment snapshot captured at creation, so impact can be measured against it.
- content_impact: measured lift for a batch between the pre-baseline audit run and a later run
  (SoV delta, alignment delta, % of gap closed), plus a per-content-type breakdown.
- content_drafts gains batch_id (which batch), content_type (richer than asset_type), and geo_score
  (denormalized from quality_notes.geo for cheap querying/sorting).

Revision ID: 0071_content_batches_impact
Revises: 0070_audit_run_mode
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op

revision = "0071_content_batches_impact"
down_revision = "0070_audit_run_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS content_batches (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL,
            gap_key TEXT NOT NULL,               -- stable id for the gap (topic / cluster label)
            gap_source TEXT DEFAULT '',           -- provenance ("audited gap: missing_owned_content")
            label TEXT DEFAULT '',
            target_topic TEXT DEFAULT '',         -- the missing_owned_content topic the batch fills
            target_prompts JSONB DEFAULT '[]'::jsonb,  -- the weak-answer prompts this gap owns
            content_types JSONB DEFAULT '[]'::jsonb,   -- the types requested (blog, article, ...)
            baseline JSONB DEFAULT '{}'::jsonb,   -- {run_id, sov, alignment, owned_rate, contested_rate, n}
            status TEXT DEFAULT 'planned',        -- planned | generating | drafted | published | measured
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_batches_biz ON content_batches(business_id, id DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS content_impact (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL,
            batch_id BIGINT,
            run_before BIGINT,                    -- audit_runs.id of the baseline
            run_after BIGINT,                     -- audit_runs.id measured against
            baseline_sov NUMERIC(6,4),
            measured_sov NUMERIC(6,4),
            sov_delta NUMERIC(6,4),
            baseline_alignment NUMERIC(6,4),
            measured_alignment NUMERIC(6,4),
            alignment_delta NUMERIC(6,4),
            gap_pct_closed NUMERIC(6,4),          -- delta / (target - baseline), clamped [0,1]
            per_type JSONB DEFAULT '{}'::jsonb,   -- {blog: {published, ...}, article: {...}}
            notes TEXT DEFAULT '',
            measured_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_content_impact_batch ON content_impact(batch_id, id DESC)")

    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS batch_id BIGINT")
    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS content_type TEXT")
    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS geo_score NUMERIC(5,1)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drafts_batch ON content_drafts(batch_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_drafts_batch")
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS geo_score")
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS content_type")
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS batch_id")
    op.execute("DROP TABLE IF EXISTS content_impact")
    op.execute("DROP TABLE IF EXISTS content_batches")
