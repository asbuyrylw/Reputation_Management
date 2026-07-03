"""citation_momentum idempotency — dedup + UNIQUE(business_id, domain, run_id) (bugfix)

BUG: citation_momentum had no uniqueness guard and citation_analytics.analyze() plain-INSERTs, so
re-running the `citation_analyze` job for the same run (audit-downstream + the run-everything
pipeline both trigger it) inserted a SECOND row per (business, domain, run). The rankings
share-of-voice endpoint then SUM(share) GROUP BY classification double-counted, surfacing
nonsense like "199% of citations from owned sources".

FIX: collapse duplicate rows (keep the newest id per key) and add a UNIQUE index so analyze() can
upsert idempotently. The share figures become correct (sum to ~1.0) immediately.

Revision ID: 0055_citation_momentum_uq
Revises: 0054_keyword_volume
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0055_citation_momentum_uq"
down_revision = "0054_keyword_volume"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Collapse existing duplicates: keep the highest id per (business_id, domain, run_id).
    op.execute("""DELETE FROM citation_momentum a USING citation_momentum b
        WHERE a.business_id = b.business_id AND a.domain = b.domain AND a.run_id = b.run_id
          AND a.id < b.id""")
    # 2. Enforce idempotency going forward.
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_citation_momentum "
               "ON citation_momentum(business_id, domain, run_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_citation_momentum")
