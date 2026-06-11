"""root_cause: persist the source-intelligence / root-cause artifact

Graph 1 (the LangGraph Root-Cause agent) fetches and analyzes the contested
SOURCE pages that feed the adverse narrative into AI answers, then synthesizes a
structured root-cause object. Persist it so the gap model + reports can ground on
"which source + which missing owned asset causes the contested surface".

Revision ID: 0003_root_cause
Revises: 0002_answers_key_sources_missing
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op

revision = "0003_root_cause"
down_revision = "0002_answers_key_sources_missing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS root_cause (
            id          BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id),
            run_id      BIGINT REFERENCES audit_runs(id),
            model       JSONB,
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_root_cause_biz ON root_cause(business_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS root_cause CASCADE")
