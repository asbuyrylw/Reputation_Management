"""discovery_targets enrichment: target type, capability tags, contacts + work-order links

Turns the outreach list from a flat table into an actionable one:
- target_type: outlet | podcast | guest_blog | guest_article | review_site | directory |
  social_account | video_platform | other.
- capabilities (TEXT[]): what the target can help with (earned_links, third_party_article,
  press_mention, podcast_guesting, reviews, video, social_amplification, directory_listing, ...).
- contact_name / contact_email / contact_phone: who to reach (best-effort auto-found, marked
  unverified, or entered manually) so the user doesn't have to hunt for it.
- discovery_target_work_orders: many-to-many link so one outlet can advance several plan items.

Revision ID: 0031_discovery_enrich
Revises: 0030_asset_publish
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0031_discovery_enrich"
down_revision = "0030_asset_publish"
branch_labels = None
depends_on = None

_COLS = [
    "target_type TEXT",
    "capabilities TEXT[]",
    "contact_name TEXT",
    "contact_email TEXT",
    "contact_phone TEXT",
    "contact_verified BOOLEAN DEFAULT FALSE",
]


def upgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE discovery_targets ADD COLUMN IF NOT EXISTS {col}")
    op.execute("""
        CREATE TABLE IF NOT EXISTS discovery_target_work_orders (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            target_id BIGINT NOT NULL REFERENCES discovery_targets(id) ON DELETE CASCADE,
            work_order_id BIGINT NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(target_id, work_order_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dtwo_biz ON discovery_target_work_orders(business_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discovery_target_work_orders")
    for col in _COLS:
        op.execute(f"ALTER TABLE discovery_targets DROP COLUMN IF EXISTS {col.split()[0]}")
