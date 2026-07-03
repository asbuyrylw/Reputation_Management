"""Phase-0 hardening regression tests.

Covers the correctness/security leak-stops:
  * build_gap_model never persists an empty/failed synthesis, and only synthesizes off a
    COMPLETED run (a budget-aborted partial run must not steer the strategy);
  * cost over_budget fail-closed is scoped PER BUSINESS and self-heals on the next good write;
  * content_generator.approve is idempotent (a double-submit mints no duplicate asset);
  * a crash mid-audit leaves a durable status='failed' run, not an orphaned in_progress one;
  * preflight_engines hard-fails before a paid audit when nothing is configured.
"""

from __future__ import annotations

import json

import pytest

from conftest import requires_db


def _seed_business(conn, name="Acme Co"):
    return conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,'acme.com','insurance','win local queries','MLM','Cincinnati OH') RETURNING id",
        (name,),
    ).fetchone()["id"]


# ---------------------------------------------------------------------------
# build_gap_model: failed/empty synthesis must not pollute outputs
# ---------------------------------------------------------------------------
@requires_db
def test_gap_model_empty_synthesis_preserves_previous(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    run_id = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at, status) VALUES (%s, now(), 'complete') RETURNING id",
        (bid,),
    ).fetchone()["id"]
    # a prior GOOD gap model that must survive a later failed synthesis
    conn.execute("INSERT INTO gap_models (business_id, run_id, model) VALUES (%s,%s,%s)",
                 (bid, run_id, json.dumps({"summary": "PRIOR GOOD"})))
    conn.commit()

    # orchestrator_json returns {} on ANY LLM failure -> must be treated as a failure
    monkeypatch.setattr(m, "orchestrator_json", lambda s, u, **k: {})
    with pytest.raises(RuntimeError):
        m.build_gap_model(bid)

    rows = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id", (bid,)).fetchall()
    assert len(rows) == 1                                   # no empty row written
    assert rows[-1]["model"]["summary"] == "PRIOR GOOD"     # previous model preserved


@requires_db
def test_gap_model_uses_large_token_cap_and_configured_tier(fresh_schema, monkeypatch):
    """Regression: the gap synthesis truncated mid-JSON at a 4000-token cap on a real
    battery. It must request ample output tokens, route to the configured (cheaper, reliable)
    tier rather than full Opus, and allow a longer timeout for the large input+output."""
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                 "VALUES (%s, now(), 'complete')", (bid,))
    conn.commit()
    captured = {}

    def fake(system, user, tier="full", max_tokens=2000, timeout=90):
        captured.update(tier=tier, max_tokens=max_tokens, timeout=timeout)
        return {"summary": "ok"}

    monkeypatch.setattr(m, "orchestrator_json", fake)
    m.build_gap_model(bid)
    assert captured["max_tokens"] >= 8000          # enough headroom -> no mid-JSON truncation
    assert captured["tier"] == m.GAP_MODEL_TIER     # configured tier (default mid/Sonnet), not full
    assert captured["timeout"] >= 120               # large synthesis can exceed the 90s default


@requires_db
def test_gap_model_synthesizes_off_completed_not_aborted_run(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    completed = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at, status) VALUES (%s, now(), 'complete') RETURNING id",
        (bid,),
    ).fetchone()["id"]
    # a NEWER aborted run (finished_at NULL) must be ignored
    conn.execute("INSERT INTO audit_runs (business_id, status) VALUES (%s, 'aborted')", (bid,))
    conn.commit()

    monkeypatch.setattr(m, "orchestrator_json", lambda s, u, **k: {"summary": "ok"})
    m.build_gap_model(bid)

    row = conn.execute("SELECT run_id FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                       (bid,)).fetchone()
    assert row["run_id"] == completed     # used the completed run, not the newer aborted one


@requires_db
def test_gap_model_requires_a_completed_run(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    conn.execute("INSERT INTO audit_runs (business_id, status) VALUES (%s, 'aborted')", (bid,))  # only aborted
    conn.commit()
    monkeypatch.setattr(m, "orchestrator_json", lambda s, u, **k: {"summary": "ok"})
    with pytest.raises(SystemExit):
        m.build_gap_model(bid)


# ---------------------------------------------------------------------------
# cost: fail-closed is per-business and self-heals
# ---------------------------------------------------------------------------
@requires_db
def test_cost_failclose_is_per_business_and_self_heals(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import cost
    cost.reset_unrecorded()
    a = _seed_business(conn, "A")
    b = _seed_business(conn, "B")
    conn.commit()

    # force ONE failed cost write for business A (simulate a transient DB blip)
    real_db = cost.db

    class _Boom:
        def __enter__(self): raise RuntimeError("db down")
        def __exit__(self, *a): return False

    monkeypatch.setattr(cost, "db", lambda: _Boom())
    cost.record(a, None, "x", "op", "m", 1, 1)     # fails -> A flagged
    monkeypatch.setattr(cost, "db", real_db)        # ledger healthy again

    assert cost.over_budget(a) is True              # A fails closed...
    assert cost.over_budget(b) is False             # ...but B is unaffected (the bug being fixed)

    cost.record(a, None, "x", "op", "m", 1, 1)      # a good write for A
    assert cost.over_budget(a) is False             # self-healed
    cost.reset_unrecorded()


# ---------------------------------------------------------------------------
# approve idempotency
# ---------------------------------------------------------------------------
@requires_db
def test_approve_is_idempotent_no_duplicate_asset(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg
    bid = _seed_business(conn)
    conn.execute(
        "INSERT INTO work_orders (business_id, wo_code, title, capability, execution, instruction, status) "
        "VALUES (%s,'WO-1','t','content_writing','auto','x','pending')", (bid,))
    conn.commit()
    monkeypatch.setattr(cg.llm, "orchestrator_text",
                        lambda system, user, max_tokens=2200, tier="full": "good content")
    monkeypatch.setattr(cg.llm, "orchestrator_json",
                        lambda system, user, tier="full": {"score": 0.9, "fixes": []}
                        if "QA reviewer" in system else {"pass": True, "flags": []})
    draft_id = cg.generate(bid)[0]

    cg.approve(draft_id, reviewer="Logan")
    cg.approve(draft_id, reviewer="Logan")   # double-submit must be a no-op

    n_assets = conn.execute("SELECT COUNT(*) n FROM assets WHERE meta->>'from_draft' = %s",
                            (str(draft_id),)).fetchone()["n"]
    assert n_assets == 1


# ---------------------------------------------------------------------------
# audit crash -> durable 'failed' run
# ---------------------------------------------------------------------------
@requires_db
def test_audit_crash_marks_run_failed(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    conn.execute("INSERT INTO business_config (business_id, samples_per_prompt, monthly_budget_usd) "
                 "VALUES (%s,1,50)", (bid,))
    conn.commit()

    class CrashEngine:
        name = "boom"; model = "x"
        def answer(self, p): raise RuntimeError("kaboom mid-battery")

    monkeypatch.setattr(m, "active_engines", lambda: [CrashEngine()])
    with pytest.raises(RuntimeError):
        m.audit(bid)

    row = conn.execute("SELECT status, finished_at FROM audit_runs WHERE business_id=%s "
                       "ORDER BY id DESC LIMIT 1", (bid,)).fetchone()
    assert row["status"] == "failed"       # durable, visible failure
    assert row["finished_at"] is None      # excluded from every trend/learning query


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------
def test_preflight_no_engines_hard_fails(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "active_engines", lambda: [])
    with pytest.raises(SystemExit):
        m.preflight_engines()


def test_preflight_returns_active_engines(monkeypatch):
    from rep_engine import ai_state_audit as m

    class E:
        name = "anthropic"; model = "claude-opus-4-8"

    monkeypatch.setattr(m, "active_engines", lambda: [E()])
    assert [e.name for e in m.preflight_engines()] == ["anthropic"]
