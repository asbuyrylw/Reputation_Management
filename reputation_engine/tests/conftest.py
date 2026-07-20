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


def _guard_test_dsn(dsn: str) -> None:
    """SAFETY: the `fresh_schema` fixture TRUNCATEs every table on REP_TEST_DSN. Refuse to run
    against a database whose name doesn't look like a throwaway test DB, so a misconfigured
    REP_TEST_DSN can never wipe real data (pointing it at the production `reputation` DB once
    destroyed live data). Override deliberately with REP_TEST_DSN_ALLOW_UNSAFE=1."""
    if os.getenv("REP_TEST_DSN_ALLOW_UNSAFE") == "1":
        return
    from urllib.parse import urlparse
    name = (urlparse(dsn).path or "").lstrip("/").split("?")[0].lower()
    if "test" not in name:
        pytest.exit(
            f"REFUSING to run: REP_TEST_DSN database '{name or dsn}' does not look like a throwaway "
            f"test DB (its name must contain 'test'). The suite TRUNCATEs every table, which would "
            f"wipe this database. Point REP_TEST_DSN at a disposable DB such as 'reputation_test', "
            f"or set REP_TEST_DSN_ALLOW_UNSAFE=1 to override.",
            returncode=2,
        )


@pytest.fixture(scope="session")
def db_dsn() -> str:
    if not REP_TEST_DSN:
        pytest.skip("REP_TEST_DSN not set")
    _guard_test_dsn(REP_TEST_DSN)
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
    "competitors", "content_drafts", "cost_ledger", "custom_prompts", "discovery_targets",
    "discovery_target_work_orders",
    "external_signals", "gap_models",
    "incidents", "learned_baseline", "learned_effectiveness", "local_rankings", "local_seo_goals",
    "mention_replies",
    "mentions", "monitor_keywords", "organizations", "pipeline_runs", "pipeline_steps",
    "plan_catalog", "production_briefs", "reports", "root_cause", "social_presence", "stripe_events",
    "subscriptions",
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


@functools.lru_cache(maxsize=1)
def _truncatable_tables(dsn: str) -> tuple[str, ...]:
    """EVERY user table in the test DB (from the live catalog), except alembic_version. Derived from
    the catalog rather than the hand-kept _ALL_TABLES so a migration that adds a table can't silently
    leave it un-truncated between tests -- that drift caused real cross-test contamination (a prior
    test's active source_documents row leaking, because business ids restart at 1 each test)."""
    import psycopg
    with psycopg.connect(dsn) as c:
        rows = c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
            "AND tablename <> 'alembic_version' ORDER BY tablename").fetchall()
    names = tuple(r[0] for r in rows)
    return names or tuple(_ALL_TABLES)   # fall back to the static list if the catalog query is empty


@pytest.fixture()
def fresh_schema(conn, db_dsn):
    """Ensure the schema exists (built once via Alembic) and truncate all tables
    between tests for isolation."""
    _ensure_schema_built()
    tables = _truncatable_tables(db_dsn)
    with conn.cursor() as cur:
        cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
        conn.commit()
    return conn
