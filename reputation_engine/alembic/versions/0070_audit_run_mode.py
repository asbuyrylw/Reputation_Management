"""audit_runs.mode: full vs the 'fast first-look' tier

Rec 9 adds a reduced-battery 'fast' audit (a real score cheaply, before the ~30-50 min full
pipeline). Runs are tagged mode='full'|'fast'. This column is REFERENCED by billing.audits_used
(a fast teaser must not consume the paid monthly audit quota) and build_gap_model (a thin fast
sample must not seed the strategy plan), so it has to exist independently of ai_state_audit.init_db
running its defensive ALTER -- otherwise a job trigger or usage-summary query that runs before the
first post-deploy audit would hit a missing column. This migration guarantees it on deploy.

Revision ID: 0070_audit_run_mode
Revises: 0069_content_dedup
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op

revision = "0070_audit_run_mode"
down_revision = "0069_content_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE audit_runs ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'full'")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_runs DROP COLUMN IF EXISTS mode")
