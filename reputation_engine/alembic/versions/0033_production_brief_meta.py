"""production_briefs: amplification playbook + why-it-helps + related work-orders

So a single content recipe carries its multi-channel distribution plan (where to post, in what
order, how to cross-share) and the plain-language reason it helps AI reputation / SEO -- the
"why and how" the owner asked for.

Revision ID: 0033_production_brief_meta
Revises: 0032_local_seo_goals
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0033_production_brief_meta"
down_revision = "0032_local_seo_goals"
branch_labels = None
depends_on = None

_COLS = [
    "amplification_playbook JSONB",
    "why_helps_ai_rep TEXT",
    "why_helps_seo TEXT",
    "related_work_orders TEXT[]",
]


def upgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE production_briefs ADD COLUMN IF NOT EXISTS {col}")


def downgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE production_briefs DROP COLUMN IF EXISTS {col.split()[0]}")
