"""Acceleration advisor integration tests -- require REP_TEST_DSN."""

from __future__ import annotations

from datetime import datetime

import pytest
from conftest import requires_db


def _biz(conn, name="Acme Co", contested="MLM"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo) "
        "VALUES (%s,'a.com','win',%s,'Cincinnati OH') RETURNING id", (name, contested)
    ).fetchone()
    conn.commit()
    return r["id"]


def _run(conn, bid, rows):
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()) RETURNING id",
                       (bid,)).fetchone()["id"]
    for ga, con in rows:
        conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
                     "goal_alignment,mentions_contested,failed) VALUES (%s,%s,'e','p','t',%s,%s,false)",
                     (rid, bid, ga, con))
    conn.commit()
    return rid


@requires_db
def test_advice_ranks_levers_and_orders_scenarios(fresh_schema):
    conn = fresh_schema
    from rep_engine import acceleration_advisor as aa
    bid = _biz(conn)
    _run(conn, bid, [(0.1, True), (0.0, True), (0.2, False)])
    out = aa.advise(bid, quiet=True)

    # every lever present and ranked by descending high-end weeks saved
    highs = [lv["weeks_saved_range"]["high"] for lv in out["levers_ranked_by_impact"]]
    assert highs == sorted(highs, reverse=True)
    assert len(out["levers_ranked_by_impact"]) == len(aa.LEVERS)

    # scenarios compress monotonically: baseline >= light >= moderate >= aggressive
    s = out["scenarios"]
    wk = lambda k: s[k]["window"]["weeks"]
    assert wk("current_plan_only") >= wk("light_lift") >= wk("moderate_lift") >= wk("aggressive_lift")


@requires_db
def test_realism_floor_caps_compression(fresh_schema):
    conn = fresh_schema
    from rep_engine import acceleration_advisor as aa
    bid = _biz(conn)
    _run(conn, bid, [(0.1, True), (0.0, True)])
    out = aa.advise(bid, quiet=True)
    base_months = out["baseline_expected_window"]["months"]
    agg_months = out["scenarios"]["aggressive_lift"]["window"]["months"]
    # aggressive can't beat 40% of baseline (the realism cap)
    assert agg_months >= round(base_months * 0.4, 1) - 0.2


@requires_db
def test_entrenchment_discounts_added_gain(fresh_schema):
    """The mechanism: a more-entrenched business applies a larger drag to the SAME
    added lever effort, so the per-unit added monthly gain is smaller. (End-to-end
    weeks-saved is confounded by baseline gain, so we check the gain mechanism directly.)"""
    conn = fresh_schema
    from rep_engine import acceleration_advisor as aa
    low = _biz(conn, "LowEnt")
    high = _biz(conn, "HighEnt")
    _run(conn, low, [(0.1, False), (0.1, False)])    # no contested -> low entrenchment
    _run(conn, high, [(0.1, True), (0.1, True)])      # all contested -> high entrenchment
    out_low = aa.advise(low, quiet=True)
    out_high = aa.advise(high, quiet=True)
    # aggressive bundle adds gain ON TOP of baseline; the added portion is smaller
    # for the more entrenched business because of the larger drag.
    base_low = aa.te.estimate(low, quiet=True)["monthly_gain_estimate"]
    base_high = aa.te.estimate(high, quiet=True)["monthly_gain_estimate"]
    added_low = out_low["scenarios"]["aggressive_lift"]["new_monthly_gain_estimate"] - base_low
    added_high = out_high["scenarios"]["aggressive_lift"]["new_monthly_gain_estimate"] - base_high
    assert added_low > added_high


@requires_db
def test_disclaimer_and_genuineness_present(fresh_schema):
    conn = fresh_schema
    from rep_engine import acceleration_advisor as aa
    bid = _biz(conn)
    _run(conn, bid, [(0.2, True)])
    out = aa.advise(bid, quiet=True)
    assert "PROJECTION" in out["disclaimer"]
    # reviews lever must carry the genuine/never-fabricated guardrail
    rev = [lv for lv in out["levers_ranked_by_impact"] if "review" in lv["unit"].lower()][0]
    assert "genuine" in rev["note"].lower() or "never fabricated" in rev["note"].lower()
