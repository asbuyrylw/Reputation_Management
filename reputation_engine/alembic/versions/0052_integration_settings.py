"""integration_settings — per-tenant automation guardrails (Integrations Phase 5)

One row per business, all auto-post OFF by safe default; every reader COALESCEs to these defaults
if the row is absent (response_policy._settings). Auto-post-enabling fields require an org-manager
to change (enforced in the router). This is the last integrations migration (0048->0052).

Revision ID: 0052_integration_settings
Revises: 0051_mention_queue_ext
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0052_integration_settings"
down_revision = "0051_mention_queue_ext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS integration_settings (
        business_id BIGINT PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
        business_timezone TEXT NOT NULL DEFAULT 'UTC',
        require_approval BOOLEAN NOT NULL DEFAULT TRUE,
        allow_owned_autopost BOOLEAN NOT NULL DEFAULT FALSE,
        auto_reply_reviews BOOLEAN NOT NULL DEFAULT FALSE,
        auto_reply_mentions BOOLEAN NOT NULL DEFAULT FALSE,
        review_rating_threshold INT NOT NULL DEFAULT 3,
        auto_reply_min_stars SMALLINT NOT NULL DEFAULT 4,
        auto_reply_max_len INT NOT NULL DEFAULT 600,
        auto_platforms JSONB DEFAULT '[]'::jsonb,
        never_auto_sentiments JSONB DEFAULT '["negative"]'::jsonb,
        daily_autopost_cap INT NOT NULL DEFAULT 10,
        hourly_auto_cap INT NOT NULL DEFAULT 3,
        warmup_manual_count INT NOT NULL DEFAULT 20,
        quiet_hours JSONB DEFAULT '{}'::jsonb,
        banned_phrases JSONB DEFAULT '[]'::jsonb,
        allowed_channels JSONB DEFAULT '[]'::jsonb,
        blocked_channels JSONB DEFAULT '["reddit","yelp"]'::jsonb,
        third_party_weekly_draft_cap INT NOT NULL DEFAULT 0,
        disclosure_text TEXT,
        notify_email BOOLEAN NOT NULL DEFAULT TRUE,
        notify_on_auto BOOLEAN NOT NULL DEFAULT TRUE,
        third_party_engage_default TEXT NOT NULL DEFAULT 'draft_alert',
        updated_by BIGINT REFERENCES users(id),
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now())""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS integration_settings")
