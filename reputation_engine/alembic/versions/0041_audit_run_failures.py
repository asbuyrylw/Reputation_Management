"""audit_runs.failed_count / failed_engines (degraded-audit alert columns)

notifications.check_and_notify and audits.py READ these columns to surface a "your last audit
was partial" alert, but no migration ever created them, so check_and_notify crashed on any DB
lacking them (taking every other alert down with it). Add them, defaulting to a non-degraded
state so existing rows read as healthy.

Revision ID: 0041_audit_run_failures
Revises: 0040_target_keywords
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0041_audit_run_failures"
down_revision = "0040_target_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS failed_count INT DEFAULT 0")
    op.execute("ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS failed_engines JSONB DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_runs DROP COLUMN IF EXISTS failed_engines")
    op.execute("ALTER TABLE audit_runs DROP COLUMN IF EXISTS failed_count")
