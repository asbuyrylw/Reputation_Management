"""api_jobs: background jobs triggered from the console (audit/cycle/etc.)

Engine work that spends LLM budget or takes minutes (audit, cycle, benchmark,
production-briefs) must never run inside an HTTP request. The console enqueues a row
here; an inline BackgroundTask (dev) or the separate worker process (durable) runs it
and records terminal status. Cycle/run jobs also write pipeline_runs/pipeline_steps
for per-step progress; this table is the single status row for every trigger.

Revision ID: 0008_api_jobs
Revises: 0007_auth
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op

revision = "0008_api_jobs"
down_revision = "0007_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS api_jobs (
            id              BIGSERIAL PRIMARY KEY,
            business_id     BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            job_type        TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'queued',  -- queued|running|complete|failed
            pipeline_run_id BIGINT,
            args            JSONB DEFAULT '{}'::jsonb,
            error           TEXT,
            requested_by    BIGINT REFERENCES users(id),
            created_at      TIMESTAMPTZ DEFAULT now(),
            started_at      TIMESTAMPTZ,
            finished_at     TIMESTAMPTZ
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_jobs_biz ON api_jobs(business_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_jobs CASCADE")
