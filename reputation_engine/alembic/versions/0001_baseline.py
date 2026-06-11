"""baseline: consolidated schema

Replaces the nine hand-applied files (schema.sql + schema_v2..v9.sql) and the
scattered in-code DDL with a single versioned baseline. The DDL in baseline.sql
was captured by pg_dump from a freshly-built database (so it is byte-exact with
what the engine has always created) and cleaned of psql meta-commands.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-10
"""
from __future__ import annotations

import pathlib

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# baseline.sql lives in the alembic/ root (one level up from versions/).
_BASELINE_SQL = (
    pathlib.Path(__file__).resolve().parents[1] / "baseline.sql"
).read_text(encoding="utf-8")

# Every table the baseline creates (used by downgrade()).
_TABLES = [
    "answers", "assets", "attribution", "audit_runs", "business_config",
    "businesses", "citation_momentum", "competitor_answers", "competitors",
    "content_drafts", "cost_ledger", "gap_models", "learned_baseline",
    "learned_effectiveness", "mention_replies", "mentions", "monitor_keywords",
    "pipeline_runs", "pipeline_steps", "site_audits", "strategy_plans",
    "work_orders",
]


def _statements(sql: str) -> list[str]:
    # The baseline DDL has no string literals containing ';', so a plain split
    # on ';' yields exactly the CREATE/ALTER statements.
    return [s.strip() for s in sql.split(";") if s.strip()]


def upgrade() -> None:
    for stmt in _statements(_BASELINE_SQL):
        op.execute(stmt)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
