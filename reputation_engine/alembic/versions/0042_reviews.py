"""reviews + gbp_snapshots — the Google review / rating data layer (NEXT)

The product recommends review campaigns and the report lists review metrics, but nothing read
the client's actual Google rating, count, or review text. This adds:
  - reviews:       per-review rows (rating/author/body/sentiment), dedup_hash-idempotent.
  - gbp_snapshots: a rating + review_count snapshot per ingest, so velocity/trend is derivable.

Read-only ingest is via Serper places (no OAuth needed). The Integrations Phase 3 design later
extends `reviews` with a platform_connections FK + a `review_replies` table for OAuth-connected
reply posting; `connection_id` is left as a plain nullable column here for that to attach to.

Revision ID: 0042_reviews
Revises: 0041_audit_run_failures
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0042_reviews"
down_revision = "0041_audit_run_failures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT,
        source TEXT NOT NULL DEFAULT 'google_business_profile',
        external_id TEXT,
        location_ref TEXT,
        author TEXT,
        rating NUMERIC(2,1),
        title TEXT,
        body TEXT,
        review_url TEXT,
        sentiment TEXT,
        status TEXT NOT NULL DEFAULT 'new',
        reviewed_at TIMESTAMPTZ,
        review_updated_at TIMESTAMPTZ,
        author_pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,
        last_seen_at TIMESTAMPTZ DEFAULT now(),
        discovered_at TIMESTAMPTZ DEFAULT now(),
        meta JSONB DEFAULT '{}'::jsonb,
        dedup_hash TEXT UNIQUE)""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_reviews_biz ON reviews(business_id, discovered_at DESC)")
    op.execute("""CREATE TABLE IF NOT EXISTS gbp_snapshots (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
        rating NUMERIC(2,1),
        review_count INT,
        place_name TEXT,
        cid TEXT,
        captured_at TIMESTAMPTZ DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gbp_snapshots_biz ON gbp_snapshots(business_id, captured_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gbp_snapshots")
    op.execute("DROP TABLE IF EXISTS reviews")
