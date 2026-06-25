"""businesses.regulatory_profile — per-tenant compliance modeling

The content compliance screen hardcoded a generic financial-firm assumption (and autofix injected
guessed broker-dealer disclosures). That misfires for an RIA, an insurance agency, or a
non-financial tenant. This stores a per-business regulatory profile that the compliance gate
adapts to:
  {firm_type: ria|broker_dealer|insurance|non_financial|other, disclosures: [str], crd, notes}

Revision ID: 0043_regulatory_profile
Revises: 0042_reviews
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0043_regulatory_profile"
down_revision = "0042_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS regulatory_profile JSONB DEFAULT '{}'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS regulatory_profile")
