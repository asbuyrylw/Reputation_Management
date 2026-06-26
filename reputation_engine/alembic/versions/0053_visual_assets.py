"""visual_assets — generated images / quote-cards / memes / video briefs (LATER: CI-4)

Tracks visual content generated for a work order / draft. Human-gated like text drafts: a visual is
'generated' until a reviewer approves it. Dormant by default -- AI image generation only runs once an
image provider key is set (rep_engine.visual_content); quote-cards render locally (no key needed).

Revision ID: 0053_visual_assets
Revises: 0052_integration_settings
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0053_visual_assets"
down_revision = "0052_integration_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS visual_assets (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        work_order_id BIGINT,
        draft_id BIGINT,
        asset_id BIGINT,
        kind TEXT NOT NULL DEFAULT 'image',        -- image|quote_card|meme|video_brief
        provider TEXT,
        model TEXT,
        prompt TEXT,
        file_path TEXT,
        url TEXT,
        width INT,
        height INT,
        status TEXT NOT NULL DEFAULT 'generated',  -- generated|approved|rejected
        compliance_note TEXT,
        reviewer TEXT,
        reviewed_at TIMESTAMPTZ,
        meta JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_visual_assets_biz ON visual_assets(business_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS visual_assets")
