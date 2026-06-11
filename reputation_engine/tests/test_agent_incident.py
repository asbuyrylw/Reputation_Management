"""Graph 4 (Reactive Incident) tests: deterministic severity/delay tools, the
low-severity log path, and the med/high human-interrupt pause-then-resume flow."""

from __future__ import annotations

from conftest import requires_db


def test_severity_and_delay_are_deterministic():
    from rep_engine import agent_incident as g
    biz = {"domain": "acme.com", "contested_terms": "MLM,scam"}
    # negative + contested source + high relevance -> high
    s, tier = g.severity_of({"sentiment": "negative", "relevance": 0.9,
                             "source_url": "https://ripoffreport.com/x"}, biz)
    assert tier == "high" and s >= 0.7
    # positive on the owned domain -> low
    s2, tier2 = g.severity_of({"sentiment": "positive", "relevance": 0.1,
                              "source_url": "https://acme.com"}, biz)
    assert tier2 == "low"
    # delay scales with severity; counters are bounded + carry suggested units
    di = g.delay_impact(0.8)
    assert di["added_weeks"] == round(0.8 * g.MAX_ADDED_WEEKS, 1)
    assert 1 <= len(di["counters"]) <= 4
    assert all("suggested_units" in c and "unit" in c for c in di["counters"])


def _biz(conn):
    bid = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, services, geo) "
        "VALUES ('Acme','acme.com','win local queries','MLM,scam','insurance','Cincinnati OH') "
        "RETURNING id").fetchone()["id"]
    conn.commit()
    return bid


@requires_db
def test_incident_low_severity_logged_without_llm(fresh_schema, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    conn = fresh_schema
    from rep_engine import agent_incident as g
    bid = _biz(conn)
    called = {"llm": 0}
    monkeypatch.setattr(g.tools, "llm_text",
                        lambda *a, **k: called.__setitem__("llm", called["llm"] + 1) or "x")
    mention = {"source_url": "https://acme.com/blog", "sentiment": "neutral",
               "relevance": 0.1, "body": "a neutral note"}
    res = g.handle_incident(bid, mention, checkpointer=InMemorySaver())
    assert res["severity"] == "low" and res["status"] == "logged"
    assert called["llm"] == 0          # low severity drafts nothing -> no token spend
    row = conn.execute("SELECT status, draft_response FROM incidents WHERE id=%s",
                       (res["incident_id"],)).fetchone()
    assert row["status"] == "logged" and row["draft_response"] is None


@requires_db
def test_incident_high_severity_pauses_then_resumes(fresh_schema, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    conn = fresh_schema
    from rep_engine import agent_incident as g
    bid = _biz(conn)
    monkeypatch.setattr(g.tools, "llm_text",
                        lambda *a, **k: "We are a licensed local insurer with strong client reviews.")
    ckpt = InMemorySaver()
    mention = {"source_url": "https://ripoffreport.com/acme", "sentiment": "negative",
               "relevance": 0.9, "external_id": "rr-1", "body": "Acme is an MLM scam, avoid"}

    res = g.handle_incident(bid, mention, checkpointer=ckpt)
    # high severity -> paused at the human gate, persisted pending with a draft + tight SLA
    assert res["severity"] == "high" and res["status"] == "pending_human_review"
    row = conn.execute("SELECT status, draft_response, sla_hours, resolved_at FROM incidents "
                       "WHERE id=%s", (res["incident_id"],)).fetchone()
    assert row["status"] == "pending_human_review"
    assert "licensed" in row["draft_response"] and row["sla_hours"] == 2
    assert row["resolved_at"] is None

    # human approves -> the graph resumes and finalizes
    g.resume_incident(bid, mention, {"approved": True}, checkpointer=ckpt)
    row2 = conn.execute("SELECT status, resolved_at FROM incidents WHERE id=%s",
                       (res["incident_id"],)).fetchone()
    assert row2["status"] == "approved" and row2["resolved_at"] is not None


@requires_db
def test_scan_triages_negative_mentions_idempotently(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import agent_incident as g
    bid = _biz(conn)
    # discover() writes to `mentions` and returns a count -- here we seed directly
    monkeypatch.setattr(g._mm, "discover", lambda business_id, quiet=True: {"found": 0})
    monkeypatch.setattr(g.tools, "llm_text", lambda *a, **k: "drafted reply")
    conn.execute("INSERT INTO mentions (business_id, source, source_url, sentiment, relevance, body) "
                 "VALUES (%s,'reddit','https://ripoffreport.com/acme','negative',0.9,'MLM scam')", (bid,))
    conn.execute("INSERT INTO mentions (business_id, source, source_url, sentiment, relevance, body) "
                 "VALUES (%s,'news','https://good.com/acme','positive',0.5,'great firm')", (bid,))
    conn.commit()

    out = g.scan(bid)
    assert len(out) == 1                       # only the negative/contested mention triaged
    assert conn.execute("SELECT COUNT(*) n FROM incidents WHERE business_id=%s",
                        (bid,)).fetchone()["n"] == 1
    # re-scan is idempotent (already-triaged mentions are excluded by the LEFT JOIN)
    g.scan(bid)
    assert conn.execute("SELECT COUNT(*) n FROM incidents WHERE business_id=%s",
                        (bid,)).fetchone()["n"] == 1


@requires_db
def test_incident_postgres_checkpointer_resumes_across_savers(fresh_schema, monkeypatch):
    """Durability: an incident paused by one PostgresSaver instance can be resumed by
    a SEPARATE instance (simulating a human reviewing in a different process)."""
    import os

    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    conn = fresh_schema
    from rep_engine import agent_incident as g
    bid = _biz(conn)
    monkeypatch.setattr(g.tools, "llm_text", lambda *a, **k: "We are a licensed local insurer.")
    dsn = os.environ["REP_TEST_DSN"]
    mention = {"source_url": "https://ripoffreport.com/acme", "sentiment": "negative",
               "relevance": 0.9, "external_id": "rr-pg", "body": "MLM scam"}

    pool_a = ConnectionPool(conninfo=dsn, min_size=1, max_size=2, open=True,
                            kwargs={"autocommit": True, "row_factory": dict_row})
    saver_a = PostgresSaver(pool_a)
    saver_a.setup()
    # clean any checkpoint left by a prior LOCAL run (CI always uses a fresh DB)
    for t in conn.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'checkpoint%' "
                          "AND tablename <> 'checkpoint_migrations'").fetchall():
        conn.execute(f"TRUNCATE {t['tablename']} CASCADE")  # nosec B608 -- pg_tables, not user input
    conn.commit()

    res = g.handle_incident(bid, mention, checkpointer=saver_a)
    assert res["status"] == "pending_human_review"
    pool_a.close()                                  # "process A" ends

    pool_b = ConnectionPool(conninfo=dsn, min_size=1, max_size=2, open=True,
                            kwargs={"autocommit": True, "row_factory": dict_row})
    saver_b = PostgresSaver(pool_b)                 # "process B": a brand-new saver
    g.resume_incident(bid, mention, {"approved": True}, checkpointer=saver_b)
    pool_b.close()

    row = conn.execute("SELECT status FROM incidents WHERE id=%s", (res["incident_id"],)).fetchone()
    assert row["status"] == "approved"              # resumed from the DURABLE checkpoint
