"""production_briefs: video + social production specs (no external API)

For channels PRODUCED OUTSIDE this system (video, social), the Production Brief
generator (rep_engine.production_brief) does not call a video/posting API and does
not draft the finished asset -- it stores a complete, human-actionable SPEC (target
query, keywords, length, format, hook, outline, CTA) that a videographer / social
manager produces off-platform. The monthly report surfaces the open ('to_produce')
briefs verbatim. A new batch supersedes the prior open set so the list never grows
unbounded.

Revision ID: 0006_production_briefs
Revises: 0005_incidents
Create Date: 2026-06-12
"""
from __future__ import annotations

from alembic import op

revision = "0006_production_briefs"
down_revision = "0005_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS production_briefs (
            id            BIGSERIAL PRIMARY KEY,
            business_id   BIGINT REFERENCES businesses(id),
            channel       TEXT,                 -- video | social
            platform      TEXT,
            title         TEXT,
            target_query  TEXT,
            brief         JSONB,                -- the full structured production spec
            status        TEXT DEFAULT 'to_produce',  -- to_produce | superseded | in_production | produced
            created_at    TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_prodbrief_biz ON production_briefs(business_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS production_briefs CASCADE")
