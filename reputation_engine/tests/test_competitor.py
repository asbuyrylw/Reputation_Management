"""Competitor benchmarking tests -- unit (mention heuristic) + integration (needs REP_TEST_DSN)."""

from __future__ import annotations

import pytest
from conftest import requires_db


# ----------------------------- unit -----------------------------
def test_mentions_by_name():
    from rep_engine import competitor as cp
    assert cp._mentions("Acme Financial is a solid choice.", [], "Acme Financial", "") is True
    assert cp._mentions("A totally different firm.", [], "Acme Financial", "") is False


def test_mentions_by_domain_in_sources():
    from rep_engine import competitor as cp
    assert cp._mentions("See their site.", ["https://rival.com/about"], "Rival", "rival.com") is True
    assert cp._mentions("No link here.", ["https://other.com"], "Rival", "rival.com") is False


def test_mentions_distinctive_token():
    from rep_engine import competitor as cp
    # distinctive token (>=4 chars) should match even without full-name match
    assert cp._mentions("People recommend Vanguard for this.", [], "Vanguard Group", "") is True
    # short tokens shouldn't cause false positives
    assert cp._mentions("The big firm downtown.", [], "AB Co", "") is False


# ----------------------------- integration -----------------------------
def _subject(conn, name="Subject Co", domain="subject.com"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo, services) "
        "VALUES (%s,%s,'win','MLM','Cincinnati OH','financial') RETURNING id", (name, domain)
    ).fetchone()
    conn.commit()
    return r["id"]


@requires_db
def test_register_competitor(fresh_schema):
    conn = fresh_schema
    from rep_engine import competitor as cp
    bid = _subject(conn)
    cid = cp.register_competitor(bid, "Rival LLC", "rival.com")
    assert cid
    # idempotent upsert on (business_id, name)
    cid2 = cp.register_competitor(bid, "Rival LLC", "rival2.com")
    assert cid2 == cid


@requires_db
def test_benchmark_and_compare(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import competitor as cp
    from rep_engine import ai_state_audit as m
    bid = _subject(conn, name="Subject Co", domain="subject.com")
    cp.register_competitor(bid, "Rival LLC", "rival.com")

    # mock engines: subject mentioned on most prompts, rival on fewer
    class E:
        name = "perplexity"; model = "sim"
        def answer(self, prompt: str) -> dict:
            p = prompt.lower()
            if "legitimate" in p:
                return m._ok("Subject Co is reputable; some compare it to Rival LLC.",
                             ["https://subject.com", "https://rival.com"])
            if "review" in p:
                return m._ok("Subject Co has strong reviews.", ["https://subject.com"])
            return m._ok("Subject Co offers financial services.", ["https://subject.com"])
    monkeypatch.setattr(m, "active_engines", lambda: [E()])

    out = cp.benchmark(bid, quiet=True)
    assert out["rows"] > 0

    cmp = cp.compare(bid, quiet=True)
    # subject should rank #1 (appears in more prompts than the rival)
    assert cmp["subject_rank"] == 1
    names = [s["name"] for s in cmp["standings"]]
    assert "Subject Co" in names and "Rival LLC" in names
    subj = next(s for s in cmp["standings"] if s["is_subject"])
    rival = next(s for s in cmp["standings"] if not s["is_subject"])
    assert subj["appearance_rate"] >= rival["appearance_rate"]
    # head-to-head should show some subject-only prompts
    assert cmp["head_to_head"][0]["subject_only_prompts"] >= 1


@requires_db
def test_compare_without_benchmark_returns_empty(fresh_schema):
    conn = fresh_schema
    from rep_engine import competitor as cp
    bid = _subject(conn)
    cp.register_competitor(bid, "Rival LLC", "rival.com")
    assert cp.compare(bid, quiet=True) == {}


@requires_db
def test_failed_calls_excluded_from_benchmark(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import competitor as cp
    from rep_engine import ai_state_audit as m
    bid = _subject(conn)
    cp.register_competitor(bid, "Rival LLC", "rival.com")

    class FailEngine:
        name = "perplexity"; model = "sim"
        def answer(self, prompt: str) -> dict:
            return m._fail("simulated outage")
    monkeypatch.setattr(m, "active_engines", lambda: [FailEngine()])

    cp.benchmark(bid, quiet=True)
    cmp = cp.compare(bid, quiet=True)
    # all calls failed -> no prompts counted as appearances for anyone
    assert cmp.get("prompts_compared", 0) == 0 or cmp["standings"][0]["appears_in"] == 0
