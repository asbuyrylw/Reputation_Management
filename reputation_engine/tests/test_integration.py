"""Integration tests -- require REP_TEST_DSN pointing at a throwaway Postgres."""

from __future__ import annotations

import json
import pytest

from conftest import requires_db


def _seed_business(conn, name="Acme Co", contested="MLM,scam"):
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (name, "acme.com", "insurance", "win local queries", contested, "Cincinnati OH"),
    ).fetchone()
    conn.commit()
    return row["id"]


@requires_db
def test_failed_calls_do_not_pollute_metrics(fresh_schema, monkeypatch):
    """The critical correctness property: a failed engine call is stored with
    NULL metrics and must NOT drag the average down."""
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = _seed_business(conn)
    conn.execute("INSERT INTO business_config (business_id, samples_per_prompt, monthly_budget_usd) "
                 "VALUES (%s,1,50)", (bid,))
    conn.commit()

    class FailEngine:
        name = "failX"; model = "x"
        def answer(self, p): return m._fail("simulated 429")

    class GoodEngine:
        name = "goodX"; model = "y"
        def answer(self, p): return m._ok("Acme is a trusted local firm.", [])

    monkeypatch.setattr(m, "active_engines", lambda: [FailEngine(), GoodEngine()])
    monkeypatch.setattr(m, "score_answer", lambda b, p, a: {
        "sentiment": "positive", "goal_alignment": 0.7,
        "mentions_contested": False, "surfaces_owned": True})

    run_id = m.audit(bid)
    failed = conn.execute("SELECT COUNT(*) n FROM answers WHERE run_id=%s AND failed", (run_id,)).fetchone()["n"]
    good = conn.execute("SELECT COUNT(*) n FROM answers WHERE run_id=%s AND NOT failed", (run_id,)).fetchone()["n"]
    avg = conn.execute("SELECT AVG(goal_alignment) ga FROM answers WHERE run_id=%s", (run_id,)).fetchone()["ga"]
    assert failed > 0 and good > 0
    # all good rows scored 0.7; failures are NULL and excluded -> avg stays 0.7
    assert abs(float(avg) - 0.7) < 1e-6


@requires_db
def test_budget_cap_blocks_audit(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m, cost
    bid = _seed_business(conn)
    conn.execute("INSERT INTO business_config (business_id, monthly_budget_usd) VALUES (%s, 0.0)", (bid,))
    # pre-load spend so we're already over the (zero) budget
    conn.execute("INSERT INTO cost_ledger (business_id, provider, operation, model, "
                 "input_tokens, output_tokens, est_cost_usd) VALUES (%s,'x','answer','x',1,1,1.0)", (bid,))
    conn.commit()
    with pytest.raises(SystemExit):
        m.audit(bid)


@requires_db
def test_tracking_lifecycle_and_attribution(fresh_schema):
    conn = fresh_schema
    from rep_engine import tracking as tr
    bid = _seed_business(conn)

    # two completed runs: baseline (bad) then improved (good)
    r1 = conn.execute("INSERT INTO audit_runs (business_id, finished_at) "
                      "VALUES (%s, now()-interval '20 days') RETURNING id", (bid,)).fetchone()["id"]
    r2 = conn.execute("INSERT INTO audit_runs (business_id, finished_at) "
                      "VALUES (%s, now()) RETURNING id", (bid,)).fetchone()["id"]
    for ga, con, own in [(0.0, True, False)]:
        conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
                     "goal_alignment,mentions_contested,surfaces_owned) "
                     "VALUES (%s,%s,'e','p','t',%s,%s,%s)", (r1, bid, ga, con, own))
    for ga, con, own in [(0.6, False, True)]:
        conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
                     "goal_alignment,mentions_contested,surfaces_owned) "
                     "VALUES (%s,%s,'e','p','t',%s,%s,%s)", (r2, bid, ga, con, own))

    # a plan to sync
    plan = {"work_orders": [
        {"wo_id": "WO-001", "title": "Baseline", "capability": "ai_visibility_tracking",
         "execution": "auto", "recommended_tool": "Module 1", "instruction": "run",
         "phase": "Phase 0", "target_date": "2026-06-09"}]}
    conn.execute("INSERT INTO strategy_plans (business_id, plan) VALUES (%s,%s)", (bid, json.dumps(plan)))
    conn.commit()

    created = tr.sync_plan(bid)
    assert created == 1

    wo_id = conn.execute("SELECT id FROM work_orders WHERE business_id=%s", (bid,)).fetchone()["id"]
    tr.set_status(wo_id, "done", assignee="tester", notes="ok")
    st = conn.execute("SELECT status, completed_at FROM work_orders WHERE id=%s", (wo_id,)).fetchone()
    assert st["status"] == "done" and st["completed_at"] is not None

    tr.log_asset(bid, "owned_page", "How we help", "https://acme.com/help", "own_site", wo_id)
    n_assets = conn.execute("SELECT COUNT(*) n FROM assets WHERE business_id=%s", (bid,)).fetchone()["n"]
    assert n_assets == 1

    out = tr.attribute(bid)
    # improved run: alignment up, contested down, owned up
    assert out["deltas"]["goal_alignment"] == pytest.approx(0.6, abs=1e-6)
    assert out["deltas"]["contested_rate"] == pytest.approx(-1.0, abs=1e-6)
    assert out["deltas"]["owned_rate"] == pytest.approx(1.0, abs=1e-6)


@requires_db
def test_alert_fires_on_contested_spike(fresh_schema):
    conn = fresh_schema
    from rep_engine import tracking as tr
    bid = _seed_business(conn)
    conn.execute("INSERT INTO business_config (business_id, alert_threshold) VALUES (%s, 0.15)", (bid,))
    r1 = conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()-interval '10 days') RETURNING id", (bid,)).fetchone()["id"]
    r2 = conn.execute("INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()) RETURNING id", (bid,)).fetchone()["id"]
    # contested goes from 0% to 100% -> well past threshold
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,mentions_contested) VALUES (%s,%s,'e','p','t',false)", (r1, bid))
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,mentions_contested) VALUES (%s,%s,'e','p','t',true)", (r2, bid))
    conn.commit()
    out = tr.check_alert(bid)
    assert out["alert"] is True
    assert out["contested_rate_jump"] == pytest.approx(1.0, abs=1e-6)


@requires_db
def test_failed_rows_excluded_from_kpi_aggregation(fresh_schema):
    """Regression: contested_rate/owned_rate aggregation must EXCLUDE failed rows.
    Failed answers store NULL metrics; counted, they dilute both headline KPIs toward
    0 in every client report, attribution row, and spike alert."""
    conn = fresh_schema
    from rep_engine import report_generator as rg, tracking as tr
    bid = _seed_business(conn)
    run_id = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at) VALUES (%s, now()) RETURNING id", (bid,)
    ).fetchone()["id"]
    # two REAL answers: contested + owned both TRUE -> true rate is 1.0 for each
    for _ in range(2):
        conn.execute(
            "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
            "goal_alignment,mentions_contested,surfaces_owned,failed) "
            "VALUES (%s,%s,'e','p','t',0.8,true,true,false)", (run_id, bid))
    # one FAILED answer with NULL metrics. If counted, each rate would fall to 2/3.
    conn.execute(
        "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
        "goal_alignment,mentions_contested,surfaces_owned,failed) "
        "VALUES (%s,%s,'e','p','',NULL,NULL,NULL,true)", (run_id, bid))
    conn.commit()

    series = rg._run_series(conn, bid)
    assert len(series) == 1
    assert series[0]["contested_rate"] == pytest.approx(1.0, abs=1e-9)
    assert series[0]["owned_rate"] == pytest.approx(1.0, abs=1e-9)

    metrics = tr._run_metrics(conn, run_id)
    assert float(metrics["contested_rate"]) == pytest.approx(1.0, abs=1e-9)
    assert float(metrics["owned_rate"]) == pytest.approx(1.0, abs=1e-9)
