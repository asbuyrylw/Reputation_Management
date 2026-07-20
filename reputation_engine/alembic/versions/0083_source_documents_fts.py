"""source_documents: FTS index + kind tag for grounded-facts retrieval (Phase G.1)

Today the corpus is dumped WHOLE into a prompt (source_material.corpus) -- no retrieval, so there's
no way to answer "do we hold facts for THIS piece?" before generating. This adds:
- kind  : a tag (pricing/differentiator/process/case_study/general) for retrieval weighting/fallback.
- a GIN FTS index over title+content so grounding_retrieval can rank docs by relevance to a topic
  with a floor, and has_grounding() can gate a pre-spend coverage check.

Additive; index is IF NOT EXISTS. (pgvector/embeddings are a deferred refinement; lexical FTS is
sufficient for a few-hundred-fact corpus.)

Revision ID: 0083_source_documents_fts
Revises: 0082_business_strategy_profile
Create Date: 2026-07-20
"""
from __future__ import annotations

from alembic import op

revision = "0083_source_documents_fts"
down_revision = "0082_business_strategy_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS kind TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_documents_fts ON source_documents "
        "USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,'')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_source_documents_fts")
    op.execute("ALTER TABLE source_documents DROP COLUMN IF EXISTS kind")
