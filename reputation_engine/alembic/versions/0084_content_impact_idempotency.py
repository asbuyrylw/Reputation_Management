"""content_impact idempotency for batch/run measurement

Revision ID: 0084_content_impact_idempotency
Revises: 0083_source_documents_fts
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op

revision = "0084_content_impact_idempotency"
down_revision = "0083_source_documents_fts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM content_impact a USING content_impact b "
        "WHERE a.id > b.id AND a.business_id=b.business_id "
        "AND a.batch_id IS NOT DISTINCT FROM b.batch_id "
        "AND a.run_after IS NOT DISTINCT FROM b.run_after "
        "AND a.batch_id IS NOT NULL AND a.run_after IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_content_impact_batch_run "
        "ON content_impact(business_id, batch_id, run_after) "
        "WHERE batch_id IS NOT NULL AND run_after IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_content_impact_batch_run")
