"""schedules + worker_heartbeat: automated, per-business recurring jobs

Turns the product from manual-trigger into a managed service: a `schedules` row says "run
job_type for this business every interval_hours". The scheduler tick enqueues due ones.
`worker_heartbeat` backs the /readyz worker-liveness check.

Revision ID: 0018_schedules
Revises: 0017_answers_entity_confusion
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0018_schedules"
down_revision = "0017_answers_entity_confusion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            job_type TEXT NOT NULL,
            interval_hours INT NOT NULL DEFAULT 168,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            next_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, job_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(enabled, next_run_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS worker_heartbeat (
            id INT PRIMARY KEY,
            last_seen TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedules")
    op.execute("DROP TABLE IF EXISTS worker_heartbeat")
