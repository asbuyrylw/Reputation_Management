"""extension_tokens: bearer tokens for the Chrome Reply Assist extension

The extension reads the pending reply queue from a browser content script on Yelp/Reddit/
Facebook, outside the console's cookie session -- it authenticates with a long-lived, revocable,
hashed bearer token scoped to one business instead. Only the sha256 hash is stored; the raw token
is shown once at creation time.

Revision ID: 0073_extension_tokens
Revises: 0072_work_order_subtasks
Create Date: 2026-07-05
"""
from __future__ import annotations

from alembic import op

revision = "0073_extension_tokens"
down_revision = "0072_work_order_subtasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS extension_tokens ("
        "id SERIAL PRIMARY KEY, "
        "business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, "
        "token_hash TEXT NOT NULL UNIQUE, "
        "label TEXT, "
        "created_by INTEGER, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "last_used_at TIMESTAMPTZ, "
        "revoked_at TIMESTAMPTZ"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_extension_tokens_business ON extension_tokens (business_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extension_tokens")
