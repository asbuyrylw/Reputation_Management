"""work_orders: rationale, gap provenance, why-it-helps, and campaign/amplification metadata

Adds the columns that turn a bare task into an explainable, traceable one:
- rationale (JSONB): {gap_ids, expected_impact, confidence, source} -- "why this task" (B1).
- gap_source / gap_specifics: which producer raised it (audit|site_crawl|local_rank|competitor)
  and the specifics (query/url/rank) so site-crawl/local-rank/competitor findings become
  actionable, traceable work (C2).
- why_helps_ai_rep / why_helps_seo: the plain-language "how this helps" shown on each task (C10).
- amplification_playbook (JSONB) / parent_work_order_id / cross_share_platforms: campaign-based
  work where one asset (e.g. a video) fans out to many channels with a posting plan (C10).

Revision ID: 0028_work_order_meta
Revises: 0027_business_industry
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op

revision = "0028_work_order_meta"
down_revision = "0027_business_industry"
branch_labels = None
depends_on = None

_COLS = [
    "rationale JSONB",
    "gap_source TEXT",
    "gap_specifics JSONB",
    "why_helps_ai_rep TEXT",
    "why_helps_seo TEXT",
    "amplification_playbook JSONB",
    "parent_work_order_id BIGINT",
    "cross_share_platforms TEXT[]",
]


def upgrade() -> None:
    for col in _COLS:
        op.execute(f"ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS {col}")


def downgrade() -> None:
    for col in _COLS:
        name = col.split()[0]
        op.execute(f"ALTER TABLE work_orders DROP COLUMN IF EXISTS {name}")
