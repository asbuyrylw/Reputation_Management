"""answers.grounded: per-answer verified-retrieval flag (Phase 1 — output credibility)

Each answer row records whether the engine actually grounded its answer in live web
retrieval (Perplexity citations, OpenAI web_search_call, Anthropic web_search_tool_result,
Gemini groundingMetadata) vs. answered from model memory. NULL = unknown / not applicable
(failed call, dry mode, or an engine with no grounding signal). Lets the audit report a
per-engine grounded_rate and flag crowd-out metrics computed off ungrounded answers.

Revision ID: 0011_answers_grounded
Revises: 0010_audit_log
Create Date: 2026-06-15
"""
from __future__ import annotations

from alembic import op

revision = "0011_answers_grounded"
down_revision = "0010_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS grounded BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE answers DROP COLUMN IF EXISTS grounded")
