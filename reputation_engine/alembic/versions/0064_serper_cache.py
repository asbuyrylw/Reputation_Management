"""serper_cache -- TTL cache for Serper responses (Phase E efficiency)

The same category-local queries are issued by the audit battery, the competitor benchmark, the
local-rank tracker, GBP ingest, and the social audit -- each hitting (and paying for) Serper fresh.
A short-TTL cache keyed on the normalized request collapses those duplicates into one paid call.

Revision ID: 0064_serper_cache
Revises: 0063_wo_area_platform
Create Date: 2026-06-27
"""
from __future__ import annotations

from alembic import op

revision = "0064_serper_cache"
down_revision = "0063_wo_area_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS serper_cache (
            cache_key   TEXT PRIMARY KEY,   -- sha256(endpoint + normalized body)
            endpoint    TEXT,
            response    JSONB,
            created_at  TIMESTAMPTZ DEFAULT now()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_serper_cache_created ON serper_cache(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS serper_cache")
