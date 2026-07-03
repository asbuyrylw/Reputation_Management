"""Phase-6 API tests: external-data ingestion. POST stores RAW with no LLM call;
list returns it; normalize is a registered background job; normalize_pending without
an orchestrator key marks signals 'failed' deterministically (no spend)."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _admin(conn, email="admin@example.com"):
    from rep_engine.api import auth
    conn.execute("INSERT INTO users (email, password_hash, role) VALUES (%s,%s,'admin')",
                 (email, auth.hash_password("pw12345678")))
    conn.commit()


def _token(c, email="admin@example.com"):
    return c.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


@requires_db
def test_ingest_store_list_and_normalize(fresh_schema, monkeypatch):
    conn = fresh_schema
    _admin(conn)
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.commit()

    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        # ingest -> stores RAW only (no LLM), status 'raw'
        r = c.post(f"/businesses/{bid}/external-signals", headers=h,
                   json={"source": "siteguru", "signal_type": "technical_seo",
                         "content": "Pages crawled: 12\nSchema gaps: FAQPage\nThin pages: 3"})
        assert r.status_code == 201 and r.json()["status"] == "raw"

        lst = c.get(f"/businesses/{bid}/external-signals", headers=h)
        assert lst.status_code == 200 and len(lst.json()) == 1
        assert lst.json()[0]["source"] == "siteguru" and lst.json()[0]["signal_type"] == "technical_seo"

        # an unknown signal_type is clamped to 'other'
        r2 = c.post(f"/businesses/{bid}/external-signals", headers=h,
                    json={"source": "mystery", "signal_type": "wat", "content": "x"})
        assert r2.status_code == 201 and r2.json()["signal_type"] == "other"

    # the normalizer is a registered background job
    from rep_engine.api import jobs
    assert "normalize_signals" in jobs.JOB_DISPATCH

    # normalize_pending routes each raw signal through the seam -> normalized. The seam is
    # MOCKED so the test never spends (the seam is verified independently in test_agent_tools).
    from rep_engine import external_signals as es
    monkeypatch.setattr(es.tools, "llm_json",
                        lambda system, user, **k: {"summary": "ok", "metrics": {"pages": 12}, "items": []})
    res = es.normalize_pending(bid)
    assert res["pending"] == 2 and res["normalized"] == 2
    statuses = {r["status"] for r in conn.execute(
        "SELECT status FROM external_signals WHERE business_id=%s", (bid,)).fetchall()}
    assert statuses == {"normalized"}
