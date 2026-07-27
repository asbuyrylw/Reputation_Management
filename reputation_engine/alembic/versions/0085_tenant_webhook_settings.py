"""tenant-scoped outbound webhook settings

Revision ID: 0085_tenant_webhook_settings
Revises: 0084_content_impact_idempotency
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op

revision = "0085_tenant_webhook_settings"
down_revision = "0084_content_impact_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE integration_settings ADD COLUMN IF NOT EXISTS webhook_url TEXT")
    op.execute("ALTER TABLE integration_settings ADD COLUMN IF NOT EXISTS webhook_secret TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE integration_settings DROP COLUMN IF EXISTS webhook_secret")
    op.execute("ALTER TABLE integration_settings DROP COLUMN IF EXISTS webhook_url")
