"""businesses.industry: separate the industry/vertical from the services list

The owner asked for services to read like LinkedIn keywords (multiple phrases:
"financial services, financial advisors, life insurance, 401k") PLUS a distinct industry
field. services stays TEXT (comma-joined) -- the engine already splits it on commas and uses
the first phrase as the primary category query, so the multi-tag UI is purely a front-end
concern over the same column. This migration only adds the new industry column.

Revision ID: 0027_business_industry
Revises: 0026_api_jobs_depends_on
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0027_business_industry"
down_revision = "0026_api_jobs_depends_on"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS industry TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS industry")
