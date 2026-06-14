"""audit_log: record write/trigger actions through the console API (deploy hardening)

Every mutating request (POST/PATCH/PUT/DELETE) is recorded with the acting user, path,
and result status by an API middleware -- an audit trail of who did what.

Revision ID: 0010_audit_log
Revises: 0009_external_signals
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op

revision = "0010_audit_log"
down_revision = "0009_external_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id          BIGSERIAL PRIMARY KEY,
            user_id     BIGINT,
            method      TEXT,
            path        TEXT,
            status_code INT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
