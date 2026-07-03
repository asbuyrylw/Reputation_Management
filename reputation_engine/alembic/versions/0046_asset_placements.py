"""asset_placements — track WHERE each asset was distributed, not just that it exists

assets carried one own_site URL, but briefs prescribe multi-surface amplification (site, GBP,
YouTube, FB, IG, LinkedIn, X). This records one row per channel an asset is/should be posted to,
with a published status + URL, so "we said amplify to 5 surfaces" becomes a tracked checklist.

Revision ID: 0046_asset_placements
Revises: 0045_wo_assignee_user
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0046_asset_placements"
down_revision = "0045_wo_assignee_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS asset_placements (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        asset_id BIGINT REFERENCES assets(id) ON DELETE CASCADE,
        channel TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned',
        url TEXT,
        published_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (asset_id, channel))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_asset_placements_biz ON asset_placements(business_id, asset_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS asset_placements")
