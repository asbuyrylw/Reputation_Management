"""target_keywords search-volume + difficulty columns (LATER: CI-5)

Adds real monthly search volume / difficulty / CPC to target_keywords, populated by an optional
provider (DataForSEO or Keywords Everywhere) when configured. Columns stay NULL until a key is set
-- the Serper grounding alone (no volume) is unchanged.

Revision ID: 0054_keyword_volume
Revises: 0053_visual_assets
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op

revision = "0054_keyword_volume"
down_revision = "0053_visual_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS search_volume INT")
    op.execute("ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS keyword_difficulty INT")
    op.execute("ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS cpc NUMERIC(8,2)")


def downgrade() -> None:
    op.execute("ALTER TABLE target_keywords DROP COLUMN IF EXISTS search_volume")
    op.execute("ALTER TABLE target_keywords DROP COLUMN IF EXISTS keyword_difficulty")
    op.execute("ALTER TABLE target_keywords DROP COLUMN IF EXISTS cpc")
