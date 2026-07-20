"""grounding_coverage: the WARN-only coverage advisory (Phase 1). Pure -- no DB, retrieve monkeypatched.

Locks the two safety invariants (coverage() is TOTAL -- never raises; blank topic -> unknown, not a
false 'ungrounded'), the status thresholds, and that plan_coverage is a pure drift-free roll-up.
"""
from __future__ import annotations

import pytest

from rep_engine import grounding_coverage as gc


def _docs(*ranks):
    return [{"id": i, "title": f"D{i}", "rank": r} for i, r in enumerate(ranks)]


def test_scope_query_precedence():
    assert gc.scope_query({"target_query": "tq", "gap_specifics": {"source_query": "sq"}, "title": "t"}) == "tq"
    assert gc.scope_query({"gap_specifics": {"source_query": "sq"}, "title": "t"}) == "sq"
    assert gc.scope_query({"title": "t"}) == "t"
    assert gc.scope_query({}) == ""
    assert gc.scope_query(None) == ""


def test_grounded_thin_ungrounded(monkeypatch):
    # >= SOLID_DOCS(2) matches AND best rank >= SOFT_RANK(0.05) -> grounded
    monkeypatch.setattr(gc._gr, "retrieve", lambda *a, **k: _docs(0.30, 0.10, 0.06))
    g = gc.coverage(1, "growth plan pricing")
    assert g["status"] == "grounded" and g["grounded"] is True and g["matched_docs"] == 3 and g["rank"] == 0.3
    assert g["note"] is None

    # exactly 1 match -> thin
    monkeypatch.setattr(gc._gr, "retrieve", lambda *a, **k: _docs(0.40))
    t = gc.coverage(1, "topic")
    assert t["status"] == "thin" and t["grounded"] is False and t["matched_docs"] == 1 and t["note"]

    # 2 matches but best rank below SOFT_RANK -> thin (barely clears the retrieval floor)
    monkeypatch.setattr(gc._gr, "retrieve", lambda *a, **k: _docs(0.03, 0.025))
    t2 = gc.coverage(1, "topic")
    assert t2["status"] == "thin"

    # zero matches -> ungrounded (corpus reachable, nothing matches)
    monkeypatch.setattr(gc._gr, "retrieve", lambda *a, **k: [])
    u = gc.coverage(1, "underwater basket weaving")
    assert u["status"] == "ungrounded" and u["grounded"] is False and u["matched_docs"] == 0 and u["note"]


def test_blank_topic_is_unknown_not_ungrounded(monkeypatch):
    called = {"n": 0}
    def _spy(*a, **k):
        called["n"] += 1
        return []
    monkeypatch.setattr(gc._gr, "retrieve", _spy)
    for blank in ("", "   ", None):
        r = gc.coverage(1, blank)
        assert r["status"] == "unknown" and r["grounded"] is None
    assert called["n"] == 0   # never even hits retrieve for a blank topic


def test_coverage_is_total_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(gc._gr, "retrieve", _boom)
    r = gc.coverage(1, "some real topic")   # must NOT raise
    assert r["status"] == "unknown" and r["grounded"] is None and r["matched_docs"] == 0 and r["rank"] == 0.0


def test_entity_risk_passthrough_never_computed(monkeypatch):
    monkeypatch.setattr(gc._gr, "retrieve", lambda *a, **k: [])
    assert gc.coverage(1, "t")["entity_risk"] is False              # default
    assert gc.coverage(1, "t", entity_risk=True)["entity_risk"] is True   # caller-supplied, not derived


def test_plan_coverage_rollup():
    sigs = [
        {"status": "grounded", "topic": "a"}, {"status": "grounded", "topic": "b"},
        {"status": "thin", "topic": "c"}, {"status": "ungrounded", "topic": "d"},
        {"status": "unknown", "topic": "e"},
    ]
    p = gc.plan_coverage(sigs)
    assert p["status"] == "gap"          # any ungrounded -> gap
    assert (p["total_topics"], p["grounded"], p["thin"], p["ungrounded"], p["unknown"]) == (5, 2, 1, 1, 1)
    assert p["ungrounded_topics"] == ["d"] and "1 of 5" in p["reason"]


def test_plan_coverage_precedence_and_empty():
    assert gc.plan_coverage([])["status"] == "unknown"
    assert gc.plan_coverage([{"status": "unknown"}, {"status": "unknown"}])["status"] == "unknown"
    assert gc.plan_coverage([{"status": "grounded"}, {"status": "thin"}])["status"] == "thin"
    assert gc.plan_coverage([{"status": "grounded"}, {"status": "grounded"}])["status"] == "ok"


# --- DB-backed: the real Postgres FTS path (not monkeypatched) locks the grounded/ungrounded line ---
from conftest import requires_db  # noqa: E402


@requires_db
def test_coverage_over_real_fts(fresh_schema):
    conn = fresh_schema
    bid = conn.execute(
        "INSERT INTO businesses (name, domain, goal, geo) VALUES ('Acme','a.com','win','Denver CO') "
        "RETURNING id").fetchone()["id"]
    for i in range(2):   # >= SOLID_DOCS strong matches so the topic is solidly grounded
        conn.execute(
            "INSERT INTO source_documents (business_id, title, source_type, content, tokens, active, kind) "
            "VALUES (%s,%s,'upload',%s,50,true,'general')",
            (bid, f"Pricing {i}", "Our annual retainer pricing for the growth plan is 2500 per month growth plan pricing."))
    conn.commit()
    g = gc.coverage(bid, "growth plan pricing retainer")
    assert g["status"] == "grounded" and g["grounded"] is True and g["matched_docs"] >= 2
    # a topic the corpus doesn't cover -> ungrounded (corpus reachable, nothing matches)
    u = gc.coverage(bid, "underwater basket weaving championship")
    assert u["status"] == "ungrounded" and u["grounded"] is False


@requires_db
def test_backfill_stamps_existing_drafts(fresh_schema):
    conn = fresh_schema
    bid = conn.execute(
        "INSERT INTO businesses (name, domain, goal, geo) VALUES ('Acme','a.com','win','Denver CO') "
        "RETURNING id").fetchone()["id"]
    for i in range(2):   # >= SOLID_DOCS so the covered topic reads "grounded", not "thin"
        conn.execute(
            "INSERT INTO source_documents (business_id, title, source_type, content, tokens, active, kind) "
            "VALUES (%s,%s,'upload',%s,50,true,'general')",
            (bid, f"Pricing {i}", "Our growth plan retainer pricing is 2500 per month growth plan pricing retainer."))
    # two existing drafts with NO coverage_advisory yet: one whose topic is grounded, one that isn't
    d_g = conn.execute(
        "INSERT INTO content_drafts (business_id, asset_type, title, body, target_query, status, quality_notes) "
        "VALUES (%s,'article','P','b','growth plan pricing retainer','pending_review','{}'::jsonb) RETURNING id",
        (bid,)).fetchone()["id"]
    d_u = conn.execute(
        "INSERT INTO content_drafts (business_id, asset_type, title, body, target_query, status, quality_notes) "
        "VALUES (%s,'article','Q','b','underwater basket weaving','pending_review',"
        "'{\"geo\":{\"score\":80}}'::jsonb) RETURNING id", (bid,)).fetchone()["id"]
    conn.commit()

    out = gc.backfill_coverage_advisory(bid)
    assert out["updated"] == 2 and out["scanned"] == 2

    rows = {r["id"]: r["quality_notes"] for r in conn.execute(
        "SELECT id, quality_notes FROM content_drafts WHERE business_id=%s", (bid,)).fetchall()}
    assert rows[d_g]["coverage_advisory"]["status"] == "grounded"
    assert rows[d_u]["coverage_advisory"]["status"] == "ungrounded"
    # merge preserved the sibling key on the second draft (|| doesn't clobber)
    assert rows[d_u]["geo"]["score"] == 80

    # idempotent: re-running doesn't duplicate or error, still one coverage_advisory key
    gc.backfill_coverage_advisory(bid)
    again = conn.execute("SELECT quality_notes FROM content_drafts WHERE id=%s", (d_g,)).fetchone()["quality_notes"]
    assert again["coverage_advisory"]["status"] == "grounded"
