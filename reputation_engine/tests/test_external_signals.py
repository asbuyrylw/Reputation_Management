"""External-data wiring: normalized external_signals feed the gap-model synthesis,
fenced as untrusted DATA (so a hostile 3rd-party report can't steer the strategy)."""

from __future__ import annotations

import json

from conftest import requires_db


@requires_db
def test_gap_model_includes_fenced_external_signals(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m

    bid = conn.execute(
        "INSERT INTO businesses (name, domain, goal) VALUES ('Acme','a.com','trust') RETURNING id"
    ).fetchone()["id"]
    conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) VALUES (%s, now(), 'complete')", (bid,))
    conn.execute(
        "INSERT INTO external_signals (business_id, source, signal_type, normalized, status) "
        "VALUES (%s,'siteguru','technical_seo',%s,'normalized')",
        (bid, json.dumps({"summary": "slow LCP on key pages", "metrics": {"lcp": 4.2}})),
    )
    conn.commit()

    captured: dict = {}

    def fake(system, user, **k):
        captured["system"], captured["user"] = system, user
        return {"summary": "ok"}

    monkeypatch.setattr(m, "orchestrator_json", fake)
    m.build_gap_model(bid)

    # the synthesis saw the external signal,
    assert "external_signals" in captured["user"]
    assert "siteguru" in captured["user"] and "slow LCP on key pages" in captured["user"]
    # fenced as untrusted DATA,
    assert m._UNTRUSTED_OPEN in captured["user"]
    # and the system prompt instructs the model to use it.
    assert "external_signals" in captured["system"]


@requires_db
def test_gap_model_unaffected_when_no_external_signals(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) VALUES (%s, now(), 'complete')", (bid,))
    conn.commit()
    captured: dict = {}
    monkeypatch.setattr(m, "orchestrator_json", lambda s, u, **k: captured.update(user=u) or {"summary": "ok"})
    m.build_gap_model(bid)
    # still present as an empty list -> no behavioral change when there's nothing to add
    assert '"external_signals": []' in captured["user"]
