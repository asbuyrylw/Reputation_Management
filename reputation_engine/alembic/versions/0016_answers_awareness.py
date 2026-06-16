"""answers.awareness: does the AI recognize this business (vs no-info)? -- awareness-gap signal

Separates an AWARENESS gap (the AI simply doesn't know the business -- a void to fill, faster)
from a NEGATIVE narrative (the AI knows it and is unfavorable -- entrenched negatives to crowd
out, slower). Powers challenge_profile() and the two-track strategy/timeline.

Revision ID: 0016_answers_awareness
Revises: 0015_auth_tokens
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op

revision = "0016_answers_awareness"
down_revision = "0015_auth_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS awareness BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE answers DROP COLUMN IF EXISTS awareness")
