"""NeuronWriter plan-enrichment cache + per-business project mapping

Turns NeuronWriter from "scores our drafts" into "shapes the whole content plan": we run a SERP+NLP
analysis for the business's priority keywords and store the term/entity recommendations, the
PAA/questions (outline material), and the competitor content scores, then feed them into the content
briefs + keyword layer.

- neuron_enrichments: one row per (business, keyword) -- the cached analysis (also our usage record).
- businesses.neuronwriter_project: each business analyzes under its OWN NeuronWriter project (so
  terms/competitors are scoped to its domain). NULL -> fall back to NEURONWRITER_PROJECT / first.

Revision ID: 0068_neuron_enrich
Revises: 0067_locations
Create Date: 2026-06-29
"""
from __future__ import annotations

from alembic import op

revision = "0068_neuron_enrich"
down_revision = "0067_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS neuron_enrichments (
            id             BIGSERIAL PRIMARY KEY,
            business_id    BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            keyword        TEXT NOT NULL,
            query_id       TEXT,
            terms          JSONB DEFAULT '{}'::jsonb,   -- {basic, extended, h1, h2}
            ideas          JSONB DEFAULT '{}'::jsonb,   -- {suggest_questions, people_also_ask, ...}
            competitors    JSONB DEFAULT '[]'::jsonb,
            content_target NUMERIC,
            created_at     TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, keyword)
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_neuron_enrich_biz ON neuron_enrichments(business_id, created_at DESC)")
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS neuronwriter_project TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS neuronwriter_project")
    op.execute("DROP TABLE IF EXISTS neuron_enrichments")
