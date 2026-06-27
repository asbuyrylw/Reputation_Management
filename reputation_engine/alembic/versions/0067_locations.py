"""business locations -- lightweight multi-location support (deferred #5a)

Today a business has one free-text `geo` ("areas served"). This adds a structured `locations` table
so a multi-location business can record each physical location (label/address/city/state/phone),
mark a primary, and surface them in the UI + NAP. Additive: `geo` keeps working unchanged and the
audit/gap/plan still run business-wide; per-location audits are a later upgrade.

Revision ID: 0067_locations
Revises: 0066_notif_user
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0067_locations"
down_revision = "0066_notif_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS locations (
            id          BIGSERIAL PRIMARY KEY,
            business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
            label       TEXT,             -- e.g. "Downtown office", "Westside branch"
            address     TEXT,
            city        TEXT,
            state       TEXT,
            postal      TEXT,
            phone       TEXT,
            is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_locations_biz ON locations(business_id, is_primary DESC, id)")
    # at most one primary per business
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_primary ON locations(business_id) "
               "WHERE is_primary")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS locations")
