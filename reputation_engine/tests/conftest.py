"""
Shared pytest fixtures for the Reputation Engine test suite.

Two kinds of tests:
  - pure-logic unit tests (no DB, no network) -- always run
  - integration tests against a real Postgres -- run only when REP_TEST_DSN is set

Set REP_TEST_DSN to a throwaway database, e.g.:
    export REP_TEST_DSN="postgresql://postgres@/reputation_test?host=/tmp&port=5433"
Integration tests create/drop their own rows and are safe to re-run.
"""

from __future__ import annotations

import os
import pytest

REP_TEST_DSN = os.getenv("REP_TEST_DSN")

# Make modules importable as `rep_engine.*` regardless of where pytest is invoked.
import sys
from pathlib import Path
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


@pytest.fixture()
def fresh_schema(conn):
    """Ensure a clean schema for an integration test. Creates tables via the
    engine's own init plus the v2 additions; truncates between tests."""
    from rep_engine import ai_state_audit as m1
    m1.init_db()
    # apply v2 columns/tables that live in schema_v2.sql
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS sample_idx INT DEFAULT 0")
        cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS failed BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS persona TEXT DEFAULT ''")
        cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''")
        for ddl in [
            """CREATE TABLE IF NOT EXISTS work_orders (id BIGSERIAL PRIMARY KEY,
               business_id BIGINT, plan_id BIGINT, wo_code TEXT, title TEXT,
               capability TEXT, execution TEXT, recommended_tool TEXT, instruction TEXT,
               phase TEXT, target_date DATE, status TEXT DEFAULT 'pending', assignee TEXT,
               started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, verified_at TIMESTAMPTZ,
               result_notes TEXT, created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS assets (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               work_order_id BIGINT, asset_type TEXT, title TEXT, url TEXT, surface TEXT,
               published_at TIMESTAMPTZ DEFAULT now(), meta JSONB DEFAULT '{}'::jsonb)""",
            """CREATE TABLE IF NOT EXISTS cost_ledger (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               run_id BIGINT, provider TEXT, operation TEXT, model TEXT, input_tokens INT,
               output_tokens INT, est_cost_usd NUMERIC(10,5), created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS attribution (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               from_run_id BIGINT, to_run_id BIGINT, metric TEXT, delta NUMERIC(8,4),
               assets_in_window JSONB, created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS business_config (business_id BIGINT PRIMARY KEY,
               disabled_tools JSONB DEFAULT '[]'::jsonb, samples_per_prompt INT DEFAULT 2,
               monthly_budget_usd NUMERIC(10,2) DEFAULT 50.0, alert_threshold NUMERIC(4,2) DEFAULT 0.15,
               updated_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS strategy_plans (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               plan JSONB, created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS site_audits (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               run_id BIGINT, summary JSONB, created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS content_drafts (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               work_order_id BIGINT, asset_type TEXT, title TEXT, body TEXT, target_query TEXT,
               quality_score NUMERIC(4,2), quality_notes JSONB DEFAULT '{}'::jsonb,
               revision_count INT DEFAULT 0, compliance_pass BOOLEAN,
               compliance_flags JSONB DEFAULT '[]'::jsonb, status TEXT DEFAULT 'pending_review',
               reviewer TEXT, reviewed_at TIMESTAMPTZ, published_asset_id BIGINT,
               created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS learned_effectiveness (business_id BIGINT, lever_type TEXT,
               obs_windows INT, obs_units INT, gain_per_unit NUMERIC(8,5), confidence TEXT,
               updated_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (business_id, lever_type))""",
            """CREATE TABLE IF NOT EXISTS learned_baseline (business_id BIGINT PRIMARY KEY,
               monthly_gain NUMERIC(8,5), obs_windows INT, confidence TEXT,
               updated_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS citation_momentum (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               domain TEXT, run_id BIGINT, cite_count INT, share NUMERIC(6,4), classification TEXT,
               first_seen_run BIGINT, last_seen_run BIGINT, created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS pipeline_runs (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               kind TEXT, status TEXT DEFAULT 'in_progress', started_at TIMESTAMPTZ DEFAULT now(),
               finished_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS pipeline_steps (id BIGSERIAL PRIMARY KEY,
               pipeline_run_id BIGINT REFERENCES pipeline_runs(id), step_key TEXT, status TEXT DEFAULT 'pending',
               error TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, UNIQUE (pipeline_run_id, step_key))""",
            """CREATE TABLE IF NOT EXISTS competitors (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               name TEXT, domain TEXT, created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (business_id, name))""",
            """CREATE TABLE IF NOT EXISTS competitor_answers (id BIGSERIAL PRIMARY KEY,
               competitor_id BIGINT REFERENCES competitors(id), business_id BIGINT, run_id BIGINT,
               engine TEXT, prompt TEXT, answer_text TEXT, cited_sources JSONB DEFAULT '[]'::jsonb,
               mentions_subject BOOLEAN, mentions_competitor BOOLEAN, sample_idx INT DEFAULT 0,
               failed BOOLEAN DEFAULT FALSE, persona TEXT DEFAULT '', location TEXT DEFAULT '',
               created_at TIMESTAMPTZ DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS monitor_keywords (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               keyword TEXT, negative BOOLEAN DEFAULT FALSE, active BOOLEAN DEFAULT TRUE,
               created_at TIMESTAMPTZ DEFAULT now(), UNIQUE (business_id, keyword))""",
            """CREATE TABLE IF NOT EXISTS mentions (id BIGSERIAL PRIMARY KEY, business_id BIGINT,
               source TEXT, source_url TEXT, external_id TEXT, author TEXT, title TEXT, body TEXT,
               matched_keyword TEXT, sentiment TEXT, relevance NUMERIC(4,3), status TEXT DEFAULT 'new',
               discovered_at TIMESTAMPTZ DEFAULT now(), dedup_hash TEXT UNIQUE)""",
            """CREATE TABLE IF NOT EXISTS mention_replies (id BIGSERIAL PRIMARY KEY,
               mention_id BIGINT REFERENCES mentions(id), business_id BIGINT, draft TEXT, tone TEXT,
               compliance_pass BOOLEAN, compliance_flags JSONB DEFAULT '[]'::jsonb,
               status TEXT DEFAULT 'pending_review', reviewer TEXT, reviewed_at TIMESTAMPTZ,
               created_at TIMESTAMPTZ DEFAULT now())""",
        ]:
            cur.execute(ddl)
        # clean slate
        for t in ["attribution", "cost_ledger", "assets", "work_orders",
                  "strategy_plans", "gap_models", "answers", "audit_runs",
                  "site_audits", "content_drafts", "learned_effectiveness",
                  "learned_baseline", "citation_momentum", "pipeline_steps",
                  "pipeline_runs", "competitor_answers", "competitors",
                  "mention_replies", "mentions", "monitor_keywords",
                  "business_config", "businesses"]:
            cur.execute(f"TRUNCATE {t} RESTART IDENTITY CASCADE")
        conn.commit()
    return conn
