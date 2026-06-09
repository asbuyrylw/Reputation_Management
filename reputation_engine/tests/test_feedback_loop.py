"""Feedback-loop integration tests -- require REP_TEST_DSN."""

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


def _run(conn, bid, when, ga):
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s,%s) RETURNING id",
                       (bid, when)).fetchone()["id"]
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,goal_alignment,failed) "
                 "VALUES (%s,%s,'e','p','t',%s,false)", (rid, bid, ga))
    conn.commit()
    return rid


def _asset(conn, bid, atype, when):
    conn.execute("INSERT INTO assets (business_id, asset_type, title, surface, published_at) "
                 "VALUES (%s,%s,'t','own_site',%s)", (bid, atype, when))
    conn.commit()


@requires_db
def test_learn_needs_two_runs(fresh_schema):
    conn = fresh_schema
    from rep_engine import feedback_loop as fb
    bid = _biz(conn)
    _run(conn, bid, datetime.now(), 0.2)
    out = fb.learn(bid, quiet=True)
    assert out["windows"] == 0
    assert out["baseline"] is None


@requires_db
def test_learn_attributes_gain_to_shipped_lever(fresh_schema):
    conn = fresh_schema
    from rep_engine import feedback_loop as fb
    bid = _biz(conn)
    t0 = datetime.now() - timedelta(days=60)
    t1 = datetime.now() - timedelta(days=30)
    t2 = datetime.now()
    _run(conn, bid, t0, 0.1)
    _run(conn, bid, t1, 0.3)   # +0.2 over 30d -> 0.2/mo
    _run(conn, bid, t2, 0.5)   # +0.2 over 30d -> 0.2/mo
    # articles shipped in window 1, reviews in window 2
    _asset(conn, bid, "article", t0 + timedelta(days=5))
    _asset(conn, bid, "article", t0 + timedelta(days=10))
    _asset(conn, bid, "review", t1 + timedelta(days=5))

    out = fb.learn(bid, quiet=True)
    assert out["windows"] == 2
    levers = out["levers"]
    # both lever families learned a positive per-unit gain
    assert "third_party_articles" in levers and levers["third_party_articles"]["gain_per_unit"] > 0
    assert "reviews" in levers and levers["reviews"]["gain_per_unit"] > 0
    # baseline mean monthly gain ~0.2
    assert out["baseline"]["monthly_gain"] == pytest.approx(0.2, abs=0.03)


@requires_db
def test_confidence_rises_with_windows(fresh_schema):
    conn = fresh_schema
    from rep_engine import feedback_loop as fb
    bid = _biz(conn)
    base = datetime.now() - timedelta(days=30 * 6)
    # 6 runs => 5 windows => high confidence baseline
    for i in range(6):
        _run(conn, bid, base + timedelta(days=30 * i), 0.1 + 0.05 * i)
    out = fb.learn(bid, quiet=True)
    assert out["windows"] == 5
    assert out["baseline"]["confidence"] == "high"


@requires_db
def test_advisor_picks_up_learned_weights(fresh_schema):
    conn = fresh_schema
    from rep_engine import feedback_loop as fb, acceleration_advisor as aa
    bid = _biz(conn)
    t0 = datetime.now() - timedelta(days=30)
    t1 = datetime.now()
    _run(conn, bid, t0, 0.1)
    _run(conn, bid, t1, 0.4)
    _asset(conn, bid, "review", t0 + timedelta(days=5))
    fb.learn(bid, quiet=True)

    out = aa.advise(bid, quiet=True)
    # at least one lever should now report a learned basis
    bases = [lv.get("weight_basis") for lv in out["levers_ranked_by_impact"]]
    assert any(b and "learned" in b for b in bases)


@requires_db
def test_learned_baseline_read_helper(fresh_schema):
    conn = fresh_schema
    from rep_engine import feedback_loop as fb
    bid = _biz(conn)
    t0 = datetime.now() - timedelta(days=30)
    t1 = datetime.now()
    _run(conn, bid, t0, 0.1)
    _run(conn, bid, t1, 0.25)
    fb.learn(bid, quiet=True)
    gain, conf = fb.learned_baseline(bid)
    assert gain == pytest.approx(0.15, abs=0.02)
    assert conf in ("low", "medium", "high")
