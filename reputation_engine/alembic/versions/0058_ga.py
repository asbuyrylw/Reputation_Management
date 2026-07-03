"""Google Analytics (GA4) data layer — ga_daily / ga_top_pages / ga_channels (Wave 1)

The BEHAVIORAL outcome layer that GSC's acquisition data can't show: sessions, users, pageviews,
conversions, engagement. Mirrors the GSC three-grain design (daily backbone + windowed top
landing-pages + channel mix). ga_top_pages carries is_our_content/asset_id so we can attribute
behavior to content WE published. Idempotent upserts; connection_id ON DELETE SET NULL (history
survives a disconnect).

Revision ID: 0058_ga
Revises: 0057_attribution_uq
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0058_ga"
down_revision = "0057_attribution_uq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS ga_daily (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        date DATE NOT NULL,
        sessions INT DEFAULT 0,
        users INT DEFAULT 0,
        pageviews INT DEFAULT 0,
        conversions NUMERIC(12,2) DEFAULT 0,
        engagement_rate NUMERIC(6,5),
        avg_session_sec NUMERIC(10,2),
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, date))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ga_daily_biz ON ga_daily(business_id, date)")

    op.execute("""CREATE TABLE IF NOT EXISTS ga_top_pages (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        page TEXT NOT NULL,
        sessions INT DEFAULT 0,
        conversions NUMERIC(12,2) DEFAULT 0,
        is_our_content BOOLEAN DEFAULT FALSE,
        asset_id BIGINT,
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, period_start, period_end, page))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ga_pages_biz ON ga_top_pages(business_id, period_end DESC, sessions DESC)")

    op.execute("""CREATE TABLE IF NOT EXISTS ga_channels (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        connection_id BIGINT REFERENCES platform_connections(id) ON DELETE SET NULL,
        property TEXT NOT NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        channel TEXT NOT NULL,
        sessions INT DEFAULT 0,
        conversions NUMERIC(12,2) DEFAULT 0,
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, property, period_start, period_end, channel))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ga_channels_biz ON ga_channels(business_id, period_end DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ga_channels")
    op.execute("DROP TABLE IF EXISTS ga_top_pages")
    op.execute("DROP TABLE IF EXISTS ga_daily")
