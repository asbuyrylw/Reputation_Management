"""assets: published URL, status, and summary for the Published-content view

When a draft is approved it becomes an asset, but nothing recorded WHERE it was published.
- published_url: the live link, entered manually for now (no site/social integration yet).
- published_status: 'pending' (approved, not yet live) | 'live'.
- summary: a short blurb for the Published list (auto-derived from the body, editable).

Revision ID: 0030_asset_publish
Revises: 0029_content_draft_review
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0030_asset_publish"
down_revision = "0029_content_draft_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS published_url TEXT")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS published_status TEXT DEFAULT 'pending'")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS summary TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS published_url")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS published_status")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS summary")
