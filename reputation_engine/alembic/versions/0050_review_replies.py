"""review_replies + reviews.connection_id FK (Integrations Phase 3)

The `reviews` table already exists (migration 0042, Serper read-only ingest). Phase 3 adds the
human-approved reply queue on top: `review_replies` (one active reply per review), and promotes
`reviews.connection_id` to a real FK on platform_connections now that that table exists. GBP review
reply is the only guarded opt-in auto-reply surface (Yelp/Facebook stay monitor-only).

Revision ID: 0050_review_replies
Revises: 0049_publish_targets
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0050_review_replies"
down_revision = "0049_publish_targets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS review_replies (
        id BIGSERIAL PRIMARY KEY,
        review_id BIGINT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        draft TEXT,
        tone TEXT,
        compliance_pass BOOLEAN,
        compliance_flags JSONB DEFAULT '[]'::jsonb,
        status TEXT NOT NULL DEFAULT 'pending_review',
        auto_generated BOOLEAN NOT NULL DEFAULT TRUE,
        reviewer TEXT,
        reviewed_at TIMESTAMPTZ,
        posted_at TIMESTAMPTZ,
        external_url TEXT,
        external_ack JSONB,
        edits JSONB DEFAULT '[]'::jsonb,
        last_error TEXT,
        job_id BIGINT REFERENCES api_jobs(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_review_replies_biz ON review_replies(business_id, status)")
    # one active reply per review (rejected/failed/superseded don't block a fresh draft)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_review_replies_active ON review_replies(review_id) "
               "WHERE status NOT IN ('rejected','failed','superseded')")
    # Promote reviews.connection_id to a real FK now that platform_connections exists.
    op.execute("""DO $$ BEGIN
        ALTER TABLE reviews ADD CONSTRAINT fk_reviews_connection
            FOREIGN KEY (connection_id) REFERENCES platform_connections(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN NULL; WHEN undefined_table THEN NULL; END $$;""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_replies")
    op.execute("""DO $$ BEGIN
        ALTER TABLE reviews DROP CONSTRAINT IF EXISTS fk_reviews_connection;
    EXCEPTION WHEN undefined_table THEN NULL; END $$;""")
