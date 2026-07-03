"""content_drafts: highlighted review sections + pre-publish placeholder checklist

- highlighted_sections (JSONB): spans the AI auto-filled for compliance (e.g. a broker-dealer
  disclosure or a bio fact pulled from the crawl/audit), rendered for the human to confirm
  accuracy before publishing.
- placeholders_pending (JSONB): the "[INSERT: ...]" markers extracted from the body, surfaced
  as a red pre-publish checklist; approval is blocked until they're all resolved.

Revision ID: 0029_content_draft_review
Revises: 0028_work_order_meta
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0029_content_draft_review"
down_revision = "0028_work_order_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS highlighted_sections JSONB")
    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS placeholders_pending JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS highlighted_sections")
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS placeholders_pending")
