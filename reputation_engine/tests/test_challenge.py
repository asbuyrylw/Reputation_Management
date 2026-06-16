"""Primary-challenge profile tests -- require REP_TEST_DSN.

Covers the awareness-vs-negative classification, the legacy (no-awareness) fallback,
the void_fill_factor ordering, and the timeline integration (an awareness gap projects
a FASTER time-to-goal than an otherwise-comparable entrenched negative narrative).
"""

from __future__ import annotations

import pytest
from conftest import requires_db


def _biz(conn, name="Acme Co"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo) "
        "VALUES (%s,'a.com','win','MLM','Cincinnati OH') RETURNING id", (name,)
    ).fetchone()
    conn.commit()
    return r["id"]


def _run(conn, bid, rows):
    """Create a finished run with answer rows: list of
    (goal_alignment, mentions_contested, sentiment, awareness)."""
    rid = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()) RETURNING id",
        (bid,),
    ).fetchone()["id"]
    for ga, con, sent, aware in rows:
        conn.execute(
            "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
            "goal_alignment,mentions_contested,sentiment,awareness,failed) "
            "VALUES (%s,%s,'e','p','t',%s,%s,%s,%s,false)",
            (rid, bid, ga, con, sent, aware),
        )
    conn.commit()
    return rid


@requires_db
def test_awareness_gap_profile(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "VoidCo")
    # mostly NOT recognized, no contested/negative among the few that are recognized
    _run(conn, bid,
         [(0.0, False, "neutral", False)] * 6 + [(0.3, False, "positive", True)] * 2)
    out = ch.challenge_profile(bid)
    assert out["profile"] == "awareness_gap"
    assert out["track"] == "fill_void"
    assert out["void_fill_factor"] == pytest.approx(1.6)
    assert out["signals"]["unaware_rate"] == pytest.approx(0.75, abs=1e-3)
    assert out["signals"]["negative_score"] == pytest.approx(0.0, abs=1e-6)


@requires_db
def test_negative_narrative_profile(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "NegCo")
    # the AI KNOWS the business and is unfavorable in most answers
    _run(conn, bid,
         [(-0.4, True, "negative", True)] * 5 + [(0.2, False, "positive", True)] * 3)
    out = ch.challenge_profile(bid)
    assert out["profile"] == "negative_narrative"
    assert out["track"] == "crowd_out"
    assert out["void_fill_factor"] == pytest.approx(0.8)
    assert out["signals"]["unaware_rate"] == pytest.approx(0.0, abs=1e-6)
    assert out["signals"]["negative_score"] >= 0.4


@requires_db
def test_mixed_profile(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "MixCo")
    # a meaningful void AND a meaningful (but not dominant) negative share
    _run(conn, bid,
         [(0.0, False, "neutral", False)] * 3
         + [(-0.3, True, "negative", True)] * 3
         + [(0.2, False, "positive", True)] * 2)
    out = ch.challenge_profile(bid)
    assert out["profile"] == "mixed"
    assert out["track"] == "both"


@requires_db
def test_established_positive_profile(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "GoodCo")
    _run(conn, bid, [(0.6, False, "positive", True)] * 6)
    out = ch.challenge_profile(bid)
    assert out["profile"] == "established_positive"
    assert out["track"] == "defend"


@requires_db
def test_unknown_when_no_run(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "EmptyCo")
    out = ch.challenge_profile(bid)
    assert out["profile"] == "unknown"
    assert out["sample_size"] == 0
    assert out["signals"]["unaware_rate"] is None


@requires_db
def test_legacy_fallback_no_awareness(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    bid = _biz(conn, "LegacyCo")
    # awareness column NULL (run scored before the awareness feature) -> fall back to
    # global contested/negative; heavy contested classifies as negative_narrative
    _run(conn, bid, [(-0.2, True, "negative", None)] * 5 + [(0.1, True, "neutral", None)] * 1)
    out = ch.challenge_profile(bid)
    assert out["signals"]["unaware_rate"] is None
    assert out["signals"]["awareness_known_n"] == 0
    assert out["profile"] == "negative_narrative"


@requires_db
def test_void_fill_factor_ordering(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    # awareness gaps fill faster than mixed, which is faster than entrenched negatives
    assert (ch.VOID_FILL_FACTORS["awareness_gap"]
            > ch.VOID_FILL_FACTORS["mixed"]
            > ch.VOID_FILL_FACTORS["negative_narrative"])


@requires_db
def test_timeline_awareness_gap_faster_than_negative(fresh_schema):
    conn = fresh_schema
    from rep_engine import challenge as ch
    from rep_engine import timeline_estimator as te
    void = _biz(conn, "VoidTimeline")
    neg = _biz(conn, "NegTimeline")
    _run(conn, void,
         [(0.0, False, "neutral", False)] * 6 + [(0.3, False, "positive", True)] * 2)
    _run(conn, neg, [(-0.2, True, "negative", True)] * 6 + [(0.2, True, "positive", True)] * 2)

    assert ch.challenge_profile(void)["profile"] == "awareness_gap"
    assert ch.challenge_profile(neg)["profile"] == "negative_narrative"

    ov = te.estimate(void)
    on = te.estimate(neg)
    # the awareness-gap business carries the void-fill boost in its baseline gain...
    assert ov["challenge"]["profile"] == "awareness_gap"
    assert "void-fill x1.6" in ov["gain_basis"]
    assert ov["monthly_gain_estimate"] == pytest.approx(0.12 * 1.6, abs=0.02)
    # ...so it gains faster and reaches dominance sooner than the negative-narrative one
    assert ov["monthly_gain_estimate"] > on["monthly_gain_estimate"]
    assert ov["projection"]["expected"]["weeks"] < on["projection"]["expected"]["weeks"]
