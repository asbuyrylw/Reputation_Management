"""
Shared pytest fixtures for the Reputation Engine test suite.

Two kinds of tests:
  - pure-logic unit tests (no DB, no network) -- always run
  - integration tests against a real Postgres -- run only when REP_TEST_DSN is set

Set REP_TEST_DSN to a throwaway database, e.g.:
    export REP_TEST_DSN="postgresql://postgres@/reputation_test?host=/tmp&port=5433"
Integration tests create/drop their own rows and are safe to re-run.

The schema is built once per session via Alembic (`alembic upgrade head`) -- the
single source of truth -- and all tables are truncated between tests. A throwaway
DB is expected; if REP_TEST_DSN points at a database that already has the old
(pre-Alembic) tables, drop it first so the baseline migration can build cleanly.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

import pytest

REP_TEST_DSN = os.getenv("REP_TEST_DSN")

# Make modules importable as `rep_engine.*` regardless of where pytest is invoked.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _have_db() -> bool:
    return bool(REP_TEST_DSN)


requires_db = pytest.mark.skipif(not _have_db(), reason="REP_TEST_DSN not set")


@pytest.fixture(scope="session")
def db_dsn() -> str:
    if not REP_TEST_DSN:
        pytest.skip("REP_TEST_DSN not set")
    # Point all modules at the test DB for the duration of the session.
    os.environ["REP_DB_DSN"] = REP_TEST_DSN
    return REP_TEST_DSN


@pytest.fixture()
def conn(db_dsn):
    import psycopg
    from psycopg.rows import dict_row
    c = psycopg.connect(db_dsn, row_factory=dict_row)
    yield c
    c.close()


# Every table the Alembic baseline creates -- truncated between tests for isolation.
_ALL_TABLES = [
    "answers", "api_jobs", "assets", "attribution", "audit_log", "audit_runs", "auth_tokens",
    "business_access",
    "business_config", "businesses", "citation_momentum", "competitor_answers",
    "competitors", "content_drafts", "cost_ledger", "discovery_targets",
    "external_signals", "gap_models",
    "incidents", "learned_baseline", "learned_effectiveness", "mention_replies",
    "mentions", "monitor_keywords", "organizations", "pipeline_runs", "pipeline_steps",
    "plan_catalog", "production_briefs", "root_cause", "stripe_events", "subscriptions",
    "site_audits", "strategy_plans", "users", "work_orders",
]


@functools.lru_cache(maxsize=1)
def _ensure_schema_built() -> None:
    """Build the schema once per session via Alembic (the single source of truth).
    Idempotent -- `upgrade head` is a no-op once the DB is at head. Reads
    REP_DB_DSN (set by the db_dsn fixture) through alembic/env.py."""
    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    # Make script_location absolute so it doesn't depend on the pytest CWD.
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture()
def fresh_schema(conn):
    """Ensure the schema exists (built once via Alembic) and truncate all tables
    between tests for isolation."""
    _ensure_schema_built()
    with conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(_ALL_TABLES) + " RESTART IDENTITY CASCADE")
        conn.commit()
    return conn
