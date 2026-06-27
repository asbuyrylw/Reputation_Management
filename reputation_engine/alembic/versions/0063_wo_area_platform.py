"""work_orders area + platform -- per-area / per-platform planning (Phase C)

The plan used to be a flat capability list grouped only by phase/week; website, blog, outreach, and
every social surface collapsed together (all social -> one "social_publishing" capability). These
columns let the plan break down by AREA (website | blog | outreach | social | local | reviews |
tracking) and, for social/local tasks, by PLATFORM (linkedin | facebook | instagram | x | youtube |
gbp | ...), so each surface gets its own concrete, trackable task.

Revision ID: 0063_wo_area_platform
Revises: 0062_social_audit
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0063_wo_area_platform"
down_revision = "0062_social_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS area TEXT")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS platform TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_area ON work_orders(business_id, area)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_work_orders_area")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS area")
    op.execute("ALTER TABLE work_orders DROP COLUMN IF EXISTS platform")
