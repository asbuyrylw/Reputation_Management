"""attribution idempotency — dedup + UNIQUE(business_id, from_run_id, to_run_id, metric) (Wave 1)

Same class of bug the citation_momentum fix addressed: `tracking.attribution()` plain-INSERTs, so a
re-run for the same run-pair duplicates the 3 metric rows. The rankings /attribution read is a
LIMIT-10 list (not a SUM) so it didn't inflate a percentage, but duplicates pollute the list with
stale entries. Collapse duplicates + enforce one row per (business, from_run, to_run, metric) so
attribution() can upsert.

Revision ID: 0057_attribution_uq
Revises: 0056_gsc
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0057_attribution_uq"
down_revision = "0056_gsc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # keep the newest id per key (NULL run-ids are legacy/test rows -> left untouched, NULLs distinct)
    op.execute("""DELETE FROM attribution a USING attribution b
        WHERE a.business_id = b.business_id
          AND a.from_run_id IS NOT DISTINCT FROM b.from_run_id
          AND a.to_run_id IS NOT DISTINCT FROM b.to_run_id
          AND a.metric = b.metric AND a.id < b.id""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_attribution_runpair "
               "ON attribution(business_id, from_run_id, to_run_id, metric)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_attribution_runpair")
