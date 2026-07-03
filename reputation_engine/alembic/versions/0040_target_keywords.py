"""target_keywords: the SEO keyword-intelligence layer (CI-1)

The ranked keyword set a business should target (primary/secondary/long_tail/local/question),
produced by keyword_research.research() from an LLM seed grounded with real Google data (Serper
relatedSearches / peopleAlsoAsk / autocomplete). Read by content generation (_grounding_context),
the gap model, and the "Keywords to rank for" view.

Revision ID: 0040_target_keywords
Revises: 0039_super_admin_billing_flags
Create Date: 2026-06-24
"""
from __future__ import annotations

from alembic import op

revision = "0040_target_keywords"
down_revision = "0039_super_admin_billing_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS target_keywords (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        keyword TEXT NOT NULL,
        kind TEXT,
        source TEXT,
        intent TEXT,
        priority INT,
        rationale TEXT,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, keyword))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_target_keywords_biz "
               "ON target_keywords(business_id, priority DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS target_keywords")
