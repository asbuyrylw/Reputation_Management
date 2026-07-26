"""Content-generator integration tests -- require REP_TEST_DSN; LLM calls mocked."""

from __future__ import annotations

import json
import pytest

from conftest import requires_db


def _seed_business(conn, name="Acme Co"):
    # A regulated-finance/insurance business (matching its data: life insurance, MLM, Cincinnati OH), so
    # the finance seams (compliance rules, GEN finance module, license policy) are exercised. industry +
    # regulatory_profile.firm_type are what the StrategyProfile keys off (6.1).
    import json as _json
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo, industry, "
        "regulatory_profile) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (name, "acme.com", "life insurance", "win local queries", "MLM", "Cincinnati OH",
         "financial services / insurance", _json.dumps({"firm_type": "insurance"})),
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

    # This test isolates the QA-score/compliance ROUTING (high score + compliant -> pending_review).
    # Neutralize the orthogonal citation-readiness HOLD gate so a deliberately trivial test body isn't
    # 'held' for being un-citable (that gate has its own coverage). Mocks take *a,**k because the real
    # orchestrator wrappers now accept bill=/max_tokens= (downstream graders pass them).
    monkeypatch.setattr(cg, "CITATION_READY_MIN", 0)
    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, *a, **k: "# How We Help Families\n\nQuality content here.")
    # high score, compliant -> should land pending_review
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, *a, **k: {"score": 0.9, "accuracy": True, "answers_query": True,
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
def test_low_quality_triggers_revision_then_held(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, *a, **k: "draft body")
    # eval always returns low score with fixes -> exhausts revisions -> needs_fix
    def fake_json(system, user, *a, **k):
        if "QA reviewer" in system:
            return {"score": 0.3, "fixes": ["add specifics"], "issues": ["too thin"]}
        return {"pass": True, "flags": []}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    # 'needs_fix' is folded into 'held' so the review queue only ever holds clean drafts.
    assert d["status"] == "held"
    assert d["revision_count"] == cg.MAX_REVISIONS  # bounded auto-revision ran


@requires_db
def test_compliance_failure_is_held(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, *a, **k: "Guaranteed 20% returns!")
    def fake_json(system, user, *a, **k):
        if "QA reviewer" in system:
            return {"score": 0.9, "fixes": []}
        return {"pass": False, "flags": ["implied guaranteed returns"]}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    # A draft that fails compliance is HELD (needs_fix folded into held) — kept out of the review queue.
    assert d["status"] == "held"
    assert d["compliance_pass"] is False
    assert "implied guaranteed returns" in json.dumps(d["compliance_flags"])


@requires_db
def test_update_draft_edits_pending_only(fresh_schema):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    did = conn.execute(
        "INSERT INTO content_drafts (business_id, asset_type, title, body, status) "
        "VALUES (%s,'article','Old title','Old body','pending') RETURNING id", (bid,),
    ).fetchone()["id"]
    conn.commit()

    # mark the draft as having passed screening (simulate the AI verdict) to prove the edit resets it
    conn.execute("UPDATE content_drafts SET compliance_pass=TRUE, quality_score=0.9 WHERE id=%s", (did,))
    conn.commit()

    # edit a pending draft -> content changes AND the stale verdict is invalidated (re-screened)
    assert cg.update_draft(did, title="New title", body="A clean body about saving.", business_id=bid) is True
    d = conn.execute("SELECT title, body, quality_score, compliance_pass FROM content_drafts WHERE id=%s", (did,)).fetchone()
    assert d["title"] == "New title" and d["body"] == "A clean body about saving."
    assert d["quality_score"] is None              # AI score cleared
    assert d["compliance_pass"] is None            # clean edit -> 'not checked yet', NOT a false pass

    # editing in a HARD compliance violation re-screens to a fail (no false 'checks passed')
    assert cg.update_draft(did, body="We offer guaranteed returns of 30%.", business_id=bid) is True
    d2 = conn.execute("SELECT compliance_pass, compliance_flags FROM content_drafts WHERE id=%s", (did,)).fetchone()
    assert d2["compliance_pass"] is False and d2["compliance_flags"]

    # tenancy: another business can't edit it
    assert cg.update_draft(did, body="hax", business_id=bid + 9999) is False
    # nothing to change -> False
    assert cg.update_draft(did, business_id=bid) is False
    # once approved it is immutable
    conn.execute("UPDATE content_drafts SET status='approved' WHERE id=%s", (did,))
    conn.commit()
    assert cg.update_draft(did, body="late edit", business_id=bid) is False
    assert "guaranteed" in conn.execute("SELECT body FROM content_drafts WHERE id=%s", (did,)).fetchone()["body"]


@requires_db
def test_approve_after_edit_promotes_edited_content(fresh_schema):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    did = conn.execute(
        "INSERT INTO content_drafts (business_id, asset_type, title, body, status) "
        "VALUES (%s,'article','Original','Original body','pending') RETURNING id", (bid,),
    ).fetchone()["id"]
    conn.commit()
    cg.update_draft(did, title="Edited title", body="Edited body", business_id=bid)
    # A clean edit leaves compliance_pass NULL ('not screened yet'), so approve() now requires a
    # principal sign-off (override_reason) to promote it — mirror that real contract here.
    cg.approve(did, reviewer="Logan", override_reason="manual editorial review OK")
    d = conn.execute("SELECT title, body, published_asset_id FROM content_drafts WHERE id=%s", (did,)).fetchone()
    assert d["title"] == "Edited title" and d["body"] == "Edited body"
    # the asset carries the EDITED title (approve snapshots title -> assets)
    a = conn.execute("SELECT title FROM assets WHERE id=%s", (d["published_asset_id"],)).fetchone()
    assert a["title"] == "Edited title"


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

    # Isolate the eval-routing behavior from the orthogonal citation-readiness hold gate.
    monkeypatch.setattr(cg, "CITATION_READY_MIN", 0)
    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, *a, **k: "decent content")

    def fake_json(system, user, *a, **k):
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
    """The non-LLM screen: the '#1/best' unverifiable-superlative rule is UNIVERSAL (every tenant); the
    finance rules (guaranteed returns, risk-free) fire ONLY for a regulated-finance tenant, so a generic
    tenant's 'risk-free trial' isn't falsely failed (6.1 Slice C). No DB / no LLM needed."""
    from rep_engine import content_generator as cg
    # universal deceptive-claims rule -> flagged for BOTH generic and finance
    assert cg._deterministic_compliance("We are the best-in-class agency") != []
    assert cg._deterministic_compliance("We are the best-in-class agency", regulated_financial=True) != []
    # finance rules -> quiet for a generic tenant, flagged only for a regulated-finance tenant
    assert cg._deterministic_compliance("We guarantee 30% returns") == []
    assert cg._deterministic_compliance("We guarantee 30% returns", regulated_financial=True) != []
    assert cg._deterministic_compliance("A totally risk-free plan") == []
    assert cg._deterministic_compliance("A totally risk-free plan", regulated_financial=True) != []
    # ordinary copy -> quiet either way
    assert cg._deterministic_compliance("Helpful, factual content for local families.") == []
    assert cg._deterministic_compliance("Helpful, factual content for local families.",
                                        regulated_financial=True) == []
    assert cg._deterministic_compliance(None) == []


@requires_db
def test_deterministic_compliance_overrides_llm_pass(fresh_schema, monkeypatch):
    """A draft that trips the non-injectable deterministic rules is non-compliant
    even when the LLM screen is coaxed into 'pass: true'."""
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    # Mocks accept **kwargs (the real orchestrator_json takes bill=/max_tokens=), so downstream
    # grading (fact_check etc.) doesn't spuriously error on an unexpected kwarg.
    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, *a, **k: "We guarantee 30% returns, risk-free.")
    # eval passes; the LLM compliance screen is spoofed to 'pass' -- deterministic wins
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, *a, **k: {"score": 0.9, "fixes": []}
                        if "QA reviewer" in system else {"pass": True, "flags": []})

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert d["compliance_pass"] is False                 # deterministic override (finance rules fire)
    # A draft that fails compliance/quality is HELD (needs_fix is folded into 'held' so the review
    # queue only ever holds clean drafts).
    assert d["status"] == "held"
    assert "guaranteed" in json.dumps(d["compliance_flags"]).lower()


@requires_db
def test_keep_best_persists_highest_scoring_revision(fresh_schema, monkeypatch):
    """A later revision can score LOWER than an earlier one; the persisted draft must be the
    highest-scoring candidate seen across rounds, not merely the last. The QA score is keyed to the
    body TEXT (not call order), so the test is robust to the extra pre-draft LLM call (outline) that
    would otherwise shift which round is 'best'. The downstream keyword / GEO / citation passes are
    neutralized so this test isolates ONLY the QA keep-best behavior it is named for."""
    import itertools
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    _seed_workorder(conn, bid)

    monkeypatch.setattr(cg, "CITATION_READY_MIN", 0)                                  # no citation-hold revise
    monkeypatch.setattr(cg, "_keyword_coverage", lambda body, grounding: {
        "covered": [], "missing": [], "important_missing": [], "rate": None})         # no keyword-coverage revise
    monkeypatch.setattr(cg, "_maximize_geo", lambda body, *a, **k: body)              # no GEO-maximize revise

    # One body carries the PEAK marker; the QA scorer gives that body 0.70 and every other 0.40 -- all
    # < QUALITY_THRESHOLD (0.75) so the loop runs to MAX_REVISIONS. PEAK sits at position 3 so it lands
    # inside the scored window regardless of how many pre-draft (outline) calls consume earlier bodies.
    bodies = itertools.chain(["draft one", "draft two", "draft PEAK three", "draft four", "draft five"],
                             (f"draft worse {n}" for n in itertools.count(6)))
    monkeypatch.setattr(cg.llm, "orchestrator_text", lambda system, user, *a, **k: next(bodies))

    def fake_json(system, user, *a, **k):
        if "QA reviewer" in system:                     # _evaluate embeds the draft body in `user`
            return {"score": 0.70 if "PEAK" in user else 0.40, "fixes": ["tighten"]}
        return {"pass": True, "flags": []}
    monkeypatch.setattr(cg.llm, "orchestrator_json", fake_json)

    created = cg.generate(bid)
    d = conn.execute("SELECT * FROM content_drafts WHERE id=%s", (created[0],)).fetchone()
    assert float(d["quality_score"]) == pytest.approx(0.70)   # the best, NOT the last (0.40)
    assert "PEAK" in d["body"]                                 # best body kept
    assert "worse" not in d["body"]
    assert d["revision_count"] == cg.MAX_REVISIONS             # revisions ATTEMPTED, unchanged
