"""answers: persist key_sources + missing from scoring

score_answer() already returns key_sources (the most influential source domains
the scorer relied on) and missing (gaps the scorer noticed), validated by
ScoreResult, but audit() only buried them inside the `raw` jsonb blob -- they
were never first-class, queryable columns. Promote them so build_gap_model and
analytics can ground strategy in them. jsonb (not text[]) to match the existing
cited_sources / compliance_flags convention.

Revision ID: 0002_answers_key_sources_missing
Revises: 0001_baseline
Create Date: 2026-06-10
"""
from __future__ import annotations

from alembic import op

revision = "0002_answers_key_sources_missing"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS key_sources jsonb DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS missing jsonb DEFAULT '[]'::jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE answers DROP COLUMN IF EXISTS missing")
    op.execute("ALTER TABLE answers DROP COLUMN IF EXISTS key_sources")
