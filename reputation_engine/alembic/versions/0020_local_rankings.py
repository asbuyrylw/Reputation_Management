"""local_rankings: Google front-page + local-pack rank tracking per category-local query

The reputation engine wins AI ANSWERS; this table backs the adjacent local-SEO battle --
ranking on page one of Google (and in the map/'places' pack) for "<service> in <city>" /
"<service> near me" searches. Rows are written by local_seo.track() from the live, geo-
targeted Serper SERP for the SUBJECT and each registered competitor. One source of truth
for the queries: ai_state_audit.category_local_prompts().

Revision ID: 0020_local_rankings
Revises: 0019_notifications
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0020_local_rankings"
down_revision = "0019_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS local_rankings (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            run_id BIGINT,
            query TEXT,
            location TEXT,
            party TEXT,
            is_subject BOOLEAN DEFAULT FALSE,
            organic_rank INT,
            local_pack_rank INT,
            on_page_one BOOLEAN DEFAULT FALSE,
            url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            found BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_rankings_biz "
        "ON local_rankings(business_id, run_id DESC, id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS local_rankings")
