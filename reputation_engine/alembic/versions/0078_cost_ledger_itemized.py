"""Extend cost_ledger for itemized, non-token (flat/unit) costs across every service.

The ledger was LLM-token-only (provider/operation/model/tokens/est_cost). This adds:
- category   : the service bucket (llm_audit, llm_gap, llm_strategy, llm_content, search, keyword_volume,
               image, video, audio, analytics, pagespeed, katteb, ...) so spend rolls up by service.
- units / unit_label : the billable unit for non-token costs (searches, keywords, images, seconds, credits).
- detail     : JSONB extras (content_type, api provider used, keyword count, endpoint, ...).

All nullable/defaulted so existing rows and the existing record() path are unaffected.
"""
from alembic import op

revision = "0078_cost_ledger_itemized"
down_revision = "0077_writing_styles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS category TEXT")
    op.execute("ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS units NUMERIC")
    op.execute("ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS unit_label TEXT")
    op.execute("ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS detail JSONB DEFAULT '{}'::jsonb")
    # backfill: everything recorded so far was an LLM call
    op.execute("UPDATE cost_ledger SET category='llm' WHERE category IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cost_ledger_cat ON cost_ledger(business_id, category, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cost_ledger_cat")
    op.execute("ALTER TABLE cost_ledger DROP COLUMN IF EXISTS detail")
    op.execute("ALTER TABLE cost_ledger DROP COLUMN IF EXISTS unit_label")
    op.execute("ALTER TABLE cost_ledger DROP COLUMN IF EXISTS units")
    op.execute("ALTER TABLE cost_ledger DROP COLUMN IF EXISTS category")
