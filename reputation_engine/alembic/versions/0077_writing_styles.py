"""writing_styles: brand writing-style profiles cloned from a URL

Analyze an existing article's writing style (tone, sentence length, vocabulary, POV, quirks) and
store a reusable profile. The ACTIVE style is injected into content_generator's voice so every
generated piece matches the brand's voice — applies to ALL our content (not just Katteb's
credit-limited article generation).

Revision ID: 0077_writing_styles
Revises: 0076_visual_blob
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op

revision = "0077_writing_styles"
down_revision = "0076_visual_blob"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS writing_styles ("
        "id SERIAL PRIMARY KEY, "
        "business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE, "
        "name TEXT NOT NULL, "
        "source_url TEXT, "
        "profile TEXT, "                       # the descriptive style guide the generator reads
        "active BOOLEAN NOT NULL DEFAULT FALSE, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_writing_styles_business ON writing_styles (business_id)")
    # at most one active style per business
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_writing_styles_active "
               "ON writing_styles (business_id) WHERE active")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS writing_styles")
