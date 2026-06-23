"""api_jobs.result: persist a job's structured outcome

run_job discarded each dispatch fn's return value, so a job that SKIPPED (e.g. local_rank
with no SERPER_API_KEY or no service area) or did measurable work (rows recorded) showed
only a bare "complete" with no explanation. We persist the structured return so the console
can show what actually happened ("Skipped -- no service area set", "Recorded 24 rankings").

Revision ID: 0024_api_jobs_result
Revises: 0023_session_revocation
Create Date: 2026-06-21
"""
from __future__ import annotations

from alembic import op

revision = "0024_api_jobs_result"
down_revision = "0023_session_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_jobs ADD COLUMN IF NOT EXISTS result JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE api_jobs DROP COLUMN IF EXISTS result")
