"""custom_prompts: user-managed prompts / topics merged into the audit battery

Owners curate their own questions/topics to track; the enabled ones flow through the
whole pipeline (audit -> gap -> content -> citations -> benchmark) via
ai_state_audit.build_prompt_battery. AI-suggested prompts are saved DISABLED for review.

Revision ID: 0021_custom_prompts
Revises: 0020_local_rankings
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "0021_custom_prompts"
down_revision = "0020_local_rankings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_prompts (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            prompt TEXT NOT NULL,
            topic TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            source TEXT NOT NULL DEFAULT 'user',
            created_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, prompt)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_custom_prompts_biz "
               "ON custom_prompts(business_id, enabled, id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS custom_prompts")
