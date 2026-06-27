"""social_presence audit fields -- own-social discovery + per-platform audit (Phase B)

Upgrades social presence from a boolean "a profile probably exists" guess into a discovered +
audited record: where the profile was found (website link = owned/confirmed vs search = inferred),
a completeness score, and per-platform findings + improvement recommendations. This is what lets
the gap model ground its social surface_actions ("improve your existing LinkedIn: <fix>" instead of
blindly "create a LinkedIn").

Revision ID: 0062_social_audit
Revises: 0061_actions_taken
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0062_social_audit"
down_revision = "0061_actions_taken"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE social_presence ADD COLUMN IF NOT EXISTS source TEXT")          # website|search|serper|none
    op.execute("ALTER TABLE social_presence ADD COLUMN IF NOT EXISTS handle TEXT")
    op.execute("ALTER TABLE social_presence ADD COLUMN IF NOT EXISTS completeness NUMERIC(4,3)")
    op.execute("ALTER TABLE social_presence ADD COLUMN IF NOT EXISTS audit JSONB DEFAULT '{}'::jsonb")


def downgrade() -> None:
    for col in ("source", "handle", "completeness", "audit"):
        op.execute(f"ALTER TABLE social_presence DROP COLUMN IF EXISTS {col}")
