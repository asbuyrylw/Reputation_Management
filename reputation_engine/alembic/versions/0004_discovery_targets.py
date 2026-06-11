"""discovery_targets: ranked outreach candidates from the Discovery agent (Graph 2)

The Discovery agent finds industry/geo journalists, outlets, podcasters and
communities for earned-media outreach. It only FINDS and RANKS them; the human
still does the outreach (the project's never-auto-contact stance), so these rows
are suggestions feeding a work queue.

Revision ID: 0004_discovery_targets
Revises: 0003_root_cause
Create Date: 2026-06-11
"""
from __future__ import annotations

from alembic import op

revision = "0004_discovery_targets"
down_revision = "0003_root_cause"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS discovery_targets (
            id          BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id),
            channel     TEXT,           -- journalist | outlet | podcast | community | guest_post
            name        TEXT,
            outlet      TEXT,
            url         TEXT,
            beat        TEXT,
            score       NUMERIC(4,2),
            rationale   TEXT,
            status      TEXT DEFAULT 'suggested',
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_discovery_biz ON discovery_targets(business_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discovery_targets CASCADE")
