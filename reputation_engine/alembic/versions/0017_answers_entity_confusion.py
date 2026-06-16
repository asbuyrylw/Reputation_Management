"""answers.entity_confusion: is the answer about a DIFFERENT same-named entity? -- disambiguation signal

Separates an ENTITY-CONFUSION / grounding failure (the AI confidently describes a different
company/person/product that merely shares the name) from both an AWARENESS gap (no info about THIS
business) and a NEGATIVE narrative (knows it and is unfavorable). Wrong-entity answers must not be
read as this business's reputation -- they are routed to a separate disambiguation metric.

Revision ID: 0017_answers_entity_confusion
Revises: 0016_answers_awareness
Create Date: 2026-06-16
"""
from __future__ import annotations

from alembic import op

revision = "0017_answers_entity_confusion"
down_revision = "0016_answers_awareness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS entity_confusion BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE answers DROP COLUMN IF EXISTS entity_confusion")
