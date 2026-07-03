"""social_presence: verified live-presence checks per platform (Phase 7)

Backs the move from "recommendation" to "confirmed gap" for social profiles. A verifier probes
LinkedIn/X/Reddit/Facebook for an actual profile; results land here so the Gaps page can show
"confirmed: no LinkedIn page" vs "page exists -- improve it", and a confirmed-absent profile
becomes a "Create profile" prerequisite task instead of an unverified suggestion.

Revision ID: 0034_social_presence
Revises: 0033_production_brief_meta
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0034_social_presence"
down_revision = "0033_production_brief_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_presence (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            exists BOOLEAN,
            profile_url TEXT,
            confidence TEXT,            -- 'verified' | 'inferred' | 'unknown'
            notes TEXT,
            last_checked_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(business_id, platform)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS social_presence")
