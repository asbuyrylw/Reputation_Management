"""Google Search Console data layer — gsc_daily / gsc_query_stats / gsc_page_stats (Wave 1)

The real organic-search OUTCOME layer (clicks/impressions/CTR/position) — the proof the SEO +
content work converts to traffic. Three grains, each tuned to its job:
  - gsc_daily: site-total, one row per (business, property, date). The cheap ROI/trend backbone,
    the only grain not distorted by per-query anonymization. NEVER auto-deleted (beats GSC's
    16-month retention -> we can show multi-year ROI Google itself cannot).
  - gsc_query_stats: top-N queries over a rolling 28-day window (windowed, not daily, to bound
    rows + dodge day-grain anonymization).
  - gsc_page_stats: top-N pages over the same window; the ATTRIBUTION grain (is_our_content +
    soft asset_id link computed at ingest by URL match).

All upserts ON CONFLICT DO UPDATE (idempotent trailing re-fetch: fresh->final overwrite).
connection_id ON DELETE SET NULL so a disconnect NEVER deletes the ROI history.

Revision ID: 0056_gsc
Revises: 0055_citation_momentum_uq
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0056_gsc"
down_revision = "0055_citation_momentum_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS gsc_daily (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        date DATE NOT NULL,
        clicks INT DEFAULT 0,
        impressions INT DEFAULT 0,
        ctr NUMERIC(6,5),
        position NUMERIC(6,2),
        data_state TEXT DEFAULT 'final',
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, date))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gsc_daily_biz ON gsc_daily(business_id, date)")

    op.execute("""CREATE TABLE IF NOT EXISTS gsc_query_stats (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        query TEXT NOT NULL,
        clicks INT DEFAULT 0,
        impressions INT DEFAULT 0,
        ctr NUMERIC(6,5),
        position NUMERIC(6,2),
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, period_start, period_end, query))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gsc_query_biz "
               "ON gsc_query_stats(business_id, period_end DESC, clicks DESC)")

    op.execute("""CREATE TABLE IF NOT EXISTS gsc_page_stats (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        page TEXT NOT NULL,
        clicks INT DEFAULT 0,
        impressions INT DEFAULT 0,
        ctr NUMERIC(6,5),
        position NUMERIC(6,2),
        is_our_content BOOLEAN DEFAULT FALSE,
        asset_id BIGINT,
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, period_start, period_end, page))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gsc_page_biz "
               "ON gsc_page_stats(business_id, period_end DESC, clicks DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_gsc_page_ours "
               "ON gsc_page_stats(business_id, period_end DESC) WHERE is_our_content")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gsc_page_stats")
    op.execute("DROP TABLE IF EXISTS gsc_query_stats")
    op.execute("DROP TABLE IF EXISTS gsc_daily")
