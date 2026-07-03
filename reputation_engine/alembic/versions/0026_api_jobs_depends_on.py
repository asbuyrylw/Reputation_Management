"""api_jobs.depends_on: explicit job dependencies

The onboarding pipeline (audit -> gap -> plan -> ... -> report) relied on the worker being a
single FIFO consumer for its ordering. With >1 worker that breaks: gap/plan/report could be
claimed before the audit finished and fail. `depends_on` (array of api_jobs.id) makes the
ordering explicit -- a worker only claims a queued job once ALL its dependencies are 'complete',
so correctness no longer depends on worker count.

Revision ID: 0026_api_jobs_depends_on
Revises: 0025_integrity_and_perf
Create Date: 2026-06-22
"""
from __future__ import annotations

from alembic import op

revision = "0026_api_jobs_depends_on"
down_revision = "0025_integrity_and_perf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_jobs ADD COLUMN IF NOT EXISTS depends_on BIGINT[]")


def downgrade() -> None:
    op.execute("ALTER TABLE api_jobs DROP COLUMN IF EXISTS depends_on")
