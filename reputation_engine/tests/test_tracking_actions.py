"""Regression tests for tracking.log_action -> the actions_taken completion log (migration 0061).

Locks the 42P10 fix. uq_actions_wo / uq_actions_brief are PARTIAL unique indexes
(``... WHERE <col> IS NOT NULL``), so the ``ON CONFLICT`` arbiter MUST repeat the predicate. A bare
``ON CONFLICT (col)`` raises 42P10 (InvalidColumnReference) at plan time and rolls back the whole
transaction -- so these tests would FAIL on that regression. Belongs to the real-Postgres suite
(require REP_TEST_DSN); part of operationalizing the hot-path-safety protocol in CI.
"""
from __future__ import annotations

from datetime import date

from conftest import requires_db


def _biz(conn, name="Acme Co"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo) "
        "VALUES (%s,'a.com','win','MLM','Cincinnati OH') RETURNING id", (name,)
    ).fetchone()
    conn.commit()
    return r["id"]


def _wo(conn, bid):
    r = conn.execute("INSERT INTO work_orders (business_id) VALUES (%s) RETURNING id", (bid,)).fetchone()
    conn.commit()
    return r["id"]


def _brief(conn, bid):
    r = conn.execute("INSERT INTO production_briefs (business_id) VALUES (%s) RETURNING id", (bid,)).fetchone()
    conn.commit()
    return r["id"]


def _count(conn, bid):
    return conn.execute("SELECT COUNT(*) AS n FROM actions_taken WHERE business_id=%s", (bid,)).fetchone()["n"]


@requires_db
def test_log_action_work_order_upsert_idempotent(fresh_schema):
    """A completion on a work order lands exactly one row and re-marking updates it in place.
    Fails with 42P10 on the pre-fix bare ``ON CONFLICT (work_order_id)``."""
    conn = fresh_schema
    from rep_engine import tracking
    bid = _biz(conn)
    wo = _wo(conn, bid)

    tracking.log_action(conn, business_id=bid, capability="content_writing", title="First",
                        completed_on=date.today(), work_order_id=wo, source="work_order")
    conn.commit()
    assert _count(conn, bid) == 1

    tracking.log_action(conn, business_id=bid, capability="content_writing", title="Updated",
                        completed_on=date.today(), work_order_id=wo, source="work_order")
    conn.commit()
    assert _count(conn, bid) == 1  # idempotent per work order -- no duplicate row
    row = conn.execute("SELECT title FROM actions_taken WHERE work_order_id=%s", (wo,)).fetchone()
    assert row["title"] == "Updated"


@requires_db
def test_log_action_production_brief_upsert_idempotent(fresh_schema):
    """Same partial-index upsert path for the production_brief key (uq_actions_brief)."""
    conn = fresh_schema
    from rep_engine import tracking
    bid = _biz(conn)
    brief = _brief(conn, bid)

    tracking.log_action(conn, business_id=bid, capability="video_creation", title="V1",
                        completed_on=date.today(), production_brief_id=brief, source="brief")
    conn.commit()
    tracking.log_action(conn, business_id=bid, capability="video_creation", title="V2",
                        completed_on=date.today(), production_brief_id=brief, source="brief")
    conn.commit()
    assert _count(conn, bid) == 1
    row = conn.execute("SELECT title FROM actions_taken WHERE production_brief_id=%s", (brief,)).fetchone()
    assert row["title"] == "V2"


@requires_db
def test_log_action_manual_no_fk_plain_insert(fresh_schema):
    """A manual action (no work_order/brief key) takes the plain-INSERT path -- each is distinct."""
    conn = fresh_schema
    from rep_engine import tracking
    bid = _biz(conn)
    tracking.log_action(conn, business_id=bid, capability="outreach", title="A",
                        completed_on=date.today(), source="manual")
    tracking.log_action(conn, business_id=bid, capability="outreach", title="B",
                        completed_on=date.today(), source="manual")
    conn.commit()
    assert _count(conn, bid) == 2
