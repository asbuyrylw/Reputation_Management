"""auth_tokens: single-use, hashed tokens for invites / password reset / email verification (Phase 2d)

We email the RAW token (in the action link) and store only its sha256 hash, so a DB read can't
mint a working link. Tokens are single-use (used_at) and expiring (expires_at).

Revision ID: 0015_auth_tokens
Revises: 0014_stripe
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0015_auth_tokens"
down_revision = "0014_stripe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS auth_tokens (
            id          BIGSERIAL PRIMARY KEY,
            user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,            -- invite | reset | verify
            token_hash  TEXT NOT NULL,            -- sha256 hex of the raw token
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_tokens CASCADE")
