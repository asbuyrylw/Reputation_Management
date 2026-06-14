"""auth: users + business_access for the web console (multi-tenant RBAC)

The CLI engine has no concept of users; the web console adds one. `users` holds
console logins (role admin|client); `business_access` maps a client user to the
business(es) they may see, with viewer|editor rights. Admins implicitly see all
businesses (business_access is ignored for them). Email uniqueness is enforced
case-insensitively via a functional index (no CITEXT extension needed).

Revision ID: 0007_auth
Revises: 0006_production_briefs
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op

revision = "0007_auth"
down_revision = "0006_production_briefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id            BIGSERIAL PRIMARY KEY,
            email         TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT,
            role          TEXT NOT NULL DEFAULT 'client',   -- admin | client
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ DEFAULT now(),
            last_login_at TIMESTAMPTZ
        )"""
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (lower(email))")
    op.execute(
        """CREATE TABLE IF NOT EXISTS business_access (
            id          BIGSERIAL PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            access_role TEXT NOT NULL DEFAULT 'viewer',      -- viewer | editor
            created_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (user_id, business_id)
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_access_user ON business_access(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS business_access CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
