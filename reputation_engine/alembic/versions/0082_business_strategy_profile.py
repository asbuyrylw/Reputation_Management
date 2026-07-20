"""businesses.strategy_profile: cached per-tenant StrategyProfile override (Phase 0.1)

Holds the OPERATOR OVERRIDE layer for a tenant's derived StrategyProfile (business_profile.derive
merges GENERIC <- industry bucket <- geo <- this override). Default '{}' means "no override" -> the
derived defaults apply. Additive/nullable; zero backfill. Nothing reads it yet (0.1 is the
foundation); later tasks thread the profile through the seams.

Revision ID: 0082_business_strategy_profile
Revises: 0081_reports_storage_key
Create Date: 2026-07-20
"""
from __future__ import annotations

from alembic import op

revision = "0082_business_strategy_profile"
down_revision = "0081_reports_storage_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS strategy_profile JSONB DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS strategy_profile")
