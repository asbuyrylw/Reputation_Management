"""Graph 3 (Multi-channel Content Remediation) tests. The LLM is mocked and the
verified content_generator._compliance gate is stubbed; the plan -> multi-channel
draft -> internal-link -> human-gate flow, persistence to content_drafts, and the
compliance routing are exercised against Postgres."""

from __future__ import annotations

from conftest import requires_db


def _biz(conn):
    bid = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, services, geo) "
        "VALUES ('Acme','acme.com','win local queries','MLM,scam','insurance','Cincinnati OH') "
        "RETURNING id").fetchone()["id"]
    conn.commit()
    return bid


@requires_db
def test_remediation_plans_drafts_links_and_gates(fresh_schema, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    conn = fresh_schema
    from rep_engine import agent_content as g
    bid = _biz(conn)

    monkeypatch.setattr(g.tools, "over_budget", lambda bid: False)
    monkeypatch.setattr(g.tools, "llm_text", lambda *a, **k: "Accurate, owned content about Acme.")
    monkeypatch.setattr(g._cg, "_compliance", lambda body: {"pass": True, "flags": []})

    def fake_json(system, user, *, business_id, tier="full", operation="agent"):
        if operation == "remediation_plan":
            return {"assets": [
                {"channel": "article", "title": "Who is Acme", "topic": "about", "keywords": ["acme"]},
                {"channel": "social_post", "platform": "reddit", "title": "Acme facts",
                 "topic": "facts", "keywords": ["acme"]}]}
        if operation == "remediation_links":
            return {"links": [{"from_id": 1, "to_id": 2, "anchor": "see also"}]}
        return {}

    monkeypatch.setattr(g.tools, "llm_json", fake_json)
    ckpt = InMemorySaver()

    res = g.remediate(bid, checkpointer=ckpt)
    assert res["status"] == "pending_human_review"      # paused at the batch human gate
    assert len(res["drafts"]) == 2 and len(res["internal_links"]) == 1
    # both assets persisted to content_drafts pending_review (per-asset publish unchanged)
    n = conn.execute("SELECT COUNT(*) n FROM content_drafts WHERE business_id=%s "
                     "AND status='pending_review'", (bid,)).fetchone()["n"]
    assert n == 2
    channels = {r["asset_type"] for r in conn.execute(
        "SELECT asset_type FROM content_drafts WHERE business_id=%s", (bid,)).fetchall()}
    assert channels == {"article", "social_post"}
    # the human resumes the bundle
    g.resume(bid, {"approved": True}, checkpointer=ckpt)


@requires_db
def test_remediation_compliance_failure_marks_needs_fix(fresh_schema, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    conn = fresh_schema
    from rep_engine import agent_content as g
    bid = _biz(conn)

    monkeypatch.setattr(g.tools, "over_budget", lambda bid: False)
    monkeypatch.setattr(g.tools, "llm_text", lambda *a, **k: "We guarantee #1 risk-free results.")
    # the verified gate blocks it
    monkeypatch.setattr(g._cg, "_compliance", lambda body: {"pass": False, "flags": ["guaranteed results"]})
    monkeypatch.setattr(g.tools, "llm_json",
                        lambda system, user, **k: {"assets": [{"channel": "article", "title": "t",
                                                               "topic": "x", "keywords": []}]}
                        if "strategist" in system else {})

    g.remediate(bid, checkpointer=InMemorySaver())
    row = conn.execute("SELECT status, compliance_pass FROM content_drafts WHERE business_id=%s LIMIT 1",
                       (bid,)).fetchone()
    assert row["status"] == "needs_fix" and row["compliance_pass"] is False


@requires_db
def test_remediation_reentry_does_not_duplicate(fresh_schema, monkeypatch):
    """Re-running remediate() while a bundle is paused must NOT duplicate drafts or
    clobber the in-flight human-gate checkpoint."""
    from langgraph.checkpoint.memory import InMemorySaver
    conn = fresh_schema
    from rep_engine import agent_content as g
    bid = _biz(conn)
    monkeypatch.setattr(g.tools, "over_budget", lambda bid: False)
    monkeypatch.setattr(g.tools, "llm_text", lambda *a, **k: "owned content")
    monkeypatch.setattr(g._cg, "_compliance", lambda body: {"pass": True, "flags": []})
    monkeypatch.setattr(g.tools, "llm_json",
                        lambda system, user, **k: {"assets": [{"channel": "article", "title": "t",
                                                               "topic": "x", "keywords": []}]}
                        if "strategist" in system else {})
    ckpt = InMemorySaver()
    r1 = g.remediate(bid, checkpointer=ckpt)
    assert r1["status"] == "pending_human_review"
    n1 = conn.execute("SELECT COUNT(*) n FROM content_drafts WHERE business_id=%s",
                      (bid,)).fetchone()["n"]
    r2 = g.remediate(bid, checkpointer=ckpt)        # re-run while paused
    assert r2.get("duplicate") is True
    n2 = conn.execute("SELECT COUNT(*) n FROM content_drafts WHERE business_id=%s",
                      (bid,)).fetchone()["n"]
    assert n2 == n1                                 # no new drafts
