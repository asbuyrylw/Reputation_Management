"""content dedup: content_hash on drafts + body_hash on assets

Replaces the old `_already_covered` no-op with real exact-content dedup. We store a sha256 of the
draft body on the draft (content_hash) and copy it onto the published asset (body_hash) at approval
time, so future generation can detect a byte-identical duplicate of already-drafted/published
content and flag it for the human (we flag, never silently drop — the "AI drafts all, human
approves" invariant). Indexed by (business_id, hash) so the lookup is cheap.

Revision ID: 0069_content_dedup
Revises: 0068_neuron_enrich
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op

revision = "0069_content_dedup"
down_revision = "0068_neuron_enrich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS content_hash TEXT")
    op.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS body_hash TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_drafts_biz_hash ON content_drafts(business_id, content_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_assets_biz_hash ON assets(business_id, body_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_assets_biz_hash")
    op.execute("DROP INDEX IF EXISTS idx_drafts_biz_hash")
    op.execute("ALTER TABLE assets DROP COLUMN IF EXISTS body_hash")
    op.execute("ALTER TABLE content_drafts DROP COLUMN IF EXISTS content_hash")
