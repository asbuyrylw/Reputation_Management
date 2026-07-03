"""public share token + white-label branding + leads (GTM follow-ups)

- businesses.public_token: an unguessable slug for the public lead-magnet audit page.
- businesses.branding: per-business white-label (brand_name / logo_url / accent) for client
  deliverables (the report + the public page). Overrides the env REPORT_BRAND_* defaults.
- leads: emails captured by the public lead-magnet page (the top-of-funnel record).

Revision ID: 0059_share_branding_leads
Revises: 0058_ga
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0059_share_branding_leads"
down_revision = "0058_ga"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS public_token TEXT")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_businesses_public_token "
               "ON businesses(public_token) WHERE public_token IS NOT NULL")
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS branding JSONB DEFAULT '{}'::jsonb")

    op.execute("""CREATE TABLE IF NOT EXISTS leads (
        id BIGSERIAL PRIMARY KEY,
        business_id BIGINT NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        name TEXT,
        source TEXT DEFAULT 'public_audit',
        meta JSONB DEFAULT '{}'::jsonb,
        captured_at TIMESTAMPTZ DEFAULT now(),
        UNIQUE (business_id, email))""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_leads_biz ON leads(business_id, captured_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leads")
    op.execute("DROP INDEX IF EXISTS uq_businesses_public_token")
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS public_token")
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS branding")
