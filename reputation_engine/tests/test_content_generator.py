"""Content-generator integration tests -- require REP_TEST_DSN; LLM calls mocked."""

from __future__ import annotations

import json
import pytest

from conftest import requires_db


def _seed_business(conn, name="Acme Co"):
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (name, "acme.com", "life insurance", "win local queries", "MLM", "Cincinnati OH"),
    ).fetchone()
    conn.commit()
    return row["id"]


def _seed_workorder(conn, bid, title="Create owned asset: How we help families",
                    capability="content_writing"):
    row = conn.execute(
        "INSERT INTO work_orders (business_id, wo_code, title, capability, execution, "
        "instruction, status) VALUES (%s,'WO-001',%s,%s,'auto','write it','pending') RETURNING id",
        (bid, title, capability),
    ).fetchone()
    conn.commit()
    return row["id"]


@requires_db
def test_generate_creates_pending_review_draft(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "# How We Help Families\n\nQuality content here.")
    # high score, compliant -> should land pending_review
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, tier="full": {"score": 0.9, "accuracy": True, "answers_query": True,
                                              "structure": True, "tone": True, "issues": [], "fixes": []}
                        if "QA reviewer" in system else {"pass": True, "flags": []})

    created = cg.generate(bid)
    assert len(created) == 1
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["status"] == "pending_review"
    assert float(d["quality_score"]) == pytest.approx(0.9)
    assert d["compliance_pass"] is True
    assert d["revision_count"] == 0


@requires_db
def test_low_quality_triggers_revision_then_needs_fix(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "draft body")
    # eval always returns low score with fixes -> exhausts revisions -> needs_fix
    def fake_json(system, user, tier="full"):
        if "QA reviewer" in system:
            return {"score": 0.3, "fixes": ["add specifics"], "issues": ["too thin"]}
        return {"pass": True, "flags": []}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["status"] == "needs_fix"
    assert d["revision_count"] == cg.MAX_REVISIONS  # bounded auto-revision ran


@requires_db
def test_compliance_failure_sets_needs_fix(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "Guaranteed 20% returns!")
    def fake_json(system, user, tier="full"):
        if "QA reviewer" in system:
            return {"score": 0.9, "fixes": []}
        return {"pass": False, "flags": ["implied guaranteed returns"]}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["status"] == "needs_fix"
    assert d["compliance_pass"] is False
    assert "implied guaranteed returns" in json.dumps(d["compliance_flags"])


@requires_db
def test_approve_promotes_to_asset_and_advances_wo(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    wo_id = _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "good content")
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, tier="full": {"score": 0.9, "fixes": []} if "QA reviewer" in system
                        else {"pass": True, "flags": []})
    draft_id = cg.generate(bid)[0]

    cg.approve(draft_id, reviewer="Logan")
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (draft_id,)).fetchone()
    assert d["status"] == "approved" and d["published_asset_id"] is not None
    # asset row created
    a = conn.execute("SELECT * FROM assets WHERE id=%s", (d["published_asset_id"],)).fetchone()
    assert a["title"] == d["title"]
    # linked work order advanced to done
    wo = conn.execute("SELECT status FROM work_orders WHERE id=%s", (wo_id,)).fetchone()
    assert wo["status"] == "done"


@requires_db
def test_compliance_unavailable_is_not_auto_passed(fresh_schema, monkeypatch):
    """If the compliance screener can't run (no LLM), it must NOT silently pass."""
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "content")
    # eval returns ok; compliance returns {} (screener unavailable)
    def fake_json(system, user, tier="full"):
        if "QA reviewer" in system:
            return {"score": 0.9, "fixes": []}
        return {}   # compliance unavailable
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    # compliance_pass is NULL (unknown) and flags note human review required
    assert d["compliance_pass"] is None
    assert "human must review" in json.dumps(d["compliance_flags"])


@requires_db
def test_eval_malformed_routes_to_human_not_needs_fix(fresh_schema, monkeypatch):
    """A malformed eval (fails EvalResult validation) must NOT become a false
    needs_fix; the draft stays pending_review with a 'human must review' flag."""
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "decent content")

    def fake_json(system, user, tier="full"):
        if "QA reviewer" in system:
            return {"score": "high"}          # malformed -> EvalResult validation fails
        return {"pass": True, "flags": []}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["status"] == "pending_review"          # NOT a false needs_fix
    assert float(d["quality_score"]) == pytest.approx(0.0)
    assert "human must review" in json.dumps(d["compliance_flags"])


def test_deterministic_compliance_rules():
    """The non-LLM screen flags hard financial-marketing violations and is quiet on
    ordinary copy -- no DB / no LLM needed."""
    from rep_engine import content_generator as cg
    assert cg._deterministic_compliance("We guarantee 30% returns") != []
    assert cg._deterministic_compliance("A totally risk-free plan") != []
    assert cg._deterministic_compliance("We are the best-in-class agency") != []
    assert cg._deterministic_compliance("Helpful, factual content for local families.") == []
    assert cg._deterministic_compliance(None) == []


@requires_db
def test_deterministic_compliance_overrides_llm_pass(fresh_schema, monkeypatch):
    """A draft that trips the non-injectable deterministic rules is non-compliant
    even when the LLM screen is coaxed into 'pass: true'."""
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "We guarantee 30% returns, risk-free.")
    # eval passes; the LLM compliance screen is spoofed to 'pass' -- deterministic wins
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, tier="full": {"score": 0.9, "fixes": []}
                        if "QA reviewer" in system else {"pass": True, "flags": []})

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["compliance_pass"] is False                 # deterministic override
    assert d["status"] == "needs_fix"
    assert "guaranteed" in json.dumps(d["compliance_flags"]).lower()
