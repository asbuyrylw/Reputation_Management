"""session revocation: users.sessions_revoked_at

Session tokens are stateless JWTs (with an `iat`). To support "sign out everywhere" / an
admin force-logout without a server-side session store, we stamp a per-user revocation time;
any token issued before it is rejected at auth time.

Revision ID: 0023_session_revocation
Revises: 0022_reports
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0023_session_revocation"
down_revision = "0022_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS sessions_revoked_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS sessions_revoked_at")
