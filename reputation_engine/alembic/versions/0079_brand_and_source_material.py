"""Brand guardrails + source-material corpus for grounded, on-brand content generation.

- businesses.brand_guardrails: hard branding/voice rules injected into EVERY generation prompt
  (e.g. Team Unstoppable: "Always brand as Team Unstoppable, never Primerica; Primerica is only the
  firm we're licensed through").
- source_documents: per-business knowledge corpus the owner uploads (brand docs, scripts, product
  sheets, testimonials). Fed to Claude + NotebookLM as grounding so content is built on the client's
  REAL facts, not generic web filler.
"""
from alembic import op

revision = "0079_brand_and_source_material"
down_revision = "0078_cost_ledger_itemized"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS brand_guardrails TEXT")
    op.execute("""
        CREATE TABLE IF NOT EXISTS source_documents (
            id           BIGSERIAL PRIMARY KEY,
            business_id  BIGINT NOT NULL,
            title        TEXT,
            source_type  TEXT DEFAULT 'upload',   -- upload | url | note | deep_research
            source_url   TEXT,
            content      TEXT,                     -- extracted plain text
            tokens       INT,                      -- approx size, for grounding-budget trimming
            active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_by   BIGINT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_docs_biz ON source_documents(business_id, active, id DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_source_docs_biz")
    op.execute("DROP TABLE IF EXISTS source_documents")
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS brand_guardrails")
