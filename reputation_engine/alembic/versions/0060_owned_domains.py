"""business owned_domains -- additional owned web properties for citation classification

The citation analyzer classifies each AI-cited domain as owned / contested / neutral. "Owned"
was only the business's primary `domain`, which (a) missed alternate properties (the owners'
personal site, a .net, an owned blog/microsite, a separate landing domain) and (b) was matched by
a buggy substring test that failed entirely when `domain` was stored as a full URL
(https://example.com/). This adds an explicit list of additional owned hosts so a client can
declare every property they control and have its citations counted as owned (subdomains included).

Revision ID: 0060_owned_domains
Revises: 0059_share_branding_leads
Create Date: 2026-06-26
"""
from __future__ import annotations

from alembic import op

revision = "0060_owned_domains"
down_revision = "0059_share_branding_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS owned_domains JSONB DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE businesses DROP COLUMN IF EXISTS owned_domains")
