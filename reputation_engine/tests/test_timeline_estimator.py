"""Timeline estimator integration tests -- require REP_TEST_DSN."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conftest import requires_db


def _biz(conn, name="Acme Co"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo) "
        "VALUES (%s,'a.com','win','MLM','Cincinnati OH') RETURNING id", (name,)
    ).fetchone()
    conn.commit()
    return r["id"]


def _run(conn, bid, when, rows):
    """Create a finished run `when` (datetime) with answer rows: list of
    (goal_alignment, mentions_contested, failed)."""
    rid = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at) VALUES (%s,%s) RETURNING id",
        (bid, when),
    ).fetchone()["id"]
    for ga, con, failed in rows:
        conn.execute(
            "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
            "goal_alignment,mentions_contested,failed) VALUES (%s,%s,'e','p','t',%s,%s,%s)",
            (rid, bid, ga, con, failed),
        )
    conn.commit()
    return rid


@requires_db
def test_baseline_estimate_low_confidence(fresh_schema):
    conn = fresh_schema
    from rep_engine import timeline_estimator as te
    bid = _biz(conn)
    # single run, low alignment, heavy contested -> low confidence, a finite range
    _run(conn, bid, datetime.now(), [(0.1, True, False), (0.0, True, False)])
    out = te.estimate(bid)
    assert out["confidence"] == "low"
    assert out["gain_basis"].startswith("baseline model")
    # projection windows are ordered optimistic <= expected <= conservative
    o = out["projection"]["optimistic"]["weeks"]
    e = out["projection"]["expected"]["weeks"]
    c = out["projection"]["conservative"]["weeks"]
    assert o <= e <= c
    assert out["remaining_gap"] > 0


@requires_db
def test_entrenchment_slows_estimate(fresh_schema):
    conn = fresh_schema
    from rep_engine import timeline_estimator as te
    low = _biz(conn, "LowEntrench")
    high = _biz(conn, "HighEntrench")
    # same low alignment; low-entrench has no contested, high-entrench all contested
    _run(conn, low, datetime.now(), [(0.1, False, False), (0.1, False, False)])
    _run(conn, high, datetime.now(), [(0.1, True, False), (0.1, True, False)])
    e_low = te.estimate(low)["projection"]["expected"]["weeks"]
    e_high = te.estimate(high)["projection"]["expected"]["weeks"]
    # more entrenched negatives => longer expected timeline
    assert e_high > e_low


@requires_db
def test_observed_velocity_takes_over(fresh_schema):
    conn = fresh_schema
    from rep_engine import timeline_estimator as te
    bid = _biz(conn)
    # two runs 30 days apart showing real improvement 0.1 -> 0.4 (=0.3/month)
    _run(conn, bid, datetime.now() - timedelta(days=30), [(0.1, True, False)])
    _run(conn, bid, datetime.now(), [(0.4, False, False)])
    out = te.estimate(bid)
    assert out["gain_basis"].startswith("observed velocity")
    assert out["confidence"] in ("medium", "high")
    # measured gain ~0.3/month; remaining gap 0.6-0.4=0.2 -> <1 month expected
    assert out["monthly_gain_estimate"] == pytest.approx(0.3, abs=0.05)
    assert out["projection"]["expected"]["months"] < 1.5


@requires_db
def test_target_already_met(fresh_schema):
    conn = fresh_schema
    from rep_engine import timeline_estimator as te
    bid = _biz(conn)
    _run(conn, bid, datetime.now(), [(0.8, False, False), (0.7, False, False)])
    out = te.estimate(bid)
    assert out["remaining_gap"] == 0
    assert "status" in out and "already met" in out["status"]


@requires_db
def test_failed_rows_excluded_from_alignment(fresh_schema):
    conn = fresh_schema
    from rep_engine import timeline_estimator as te
    bid = _biz(conn)
    # one good 0.5 row + one failed NULL-metric row; alignment should be 0.5 not dragged
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()) RETURNING id",
                       (bid,)).fetchone()["id"]
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,goal_alignment,failed) "
                 "VALUES (%s,%s,'e','p','t',0.5,false)", (rid, bid))
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,goal_alignment,failed) "
                 "VALUES (%s,%s,'e','p','',NULL,true)", (rid, bid))
    conn.commit()
    out = te.estimate(bid)
    assert out["current_alignment"] == pytest.approx(0.5, abs=1e-6)
