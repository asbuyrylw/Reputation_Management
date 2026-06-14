"""Phase-2 API read tests: audit-runs (+ per-run metrics), run answers, before/after,
site-audit, gap-model. Each is tenancy-guarded by the same authorize_business dep."""

from __future__ import annotations

import json
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


def _token(client, email="admin@example.com"):
    return client.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


def _seed_data(conn):
    bid = conn.execute("INSERT INTO businesses (name, domain, contested_terms) "
                       "VALUES ('Acme','acme.com','MLM,scam') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                       "VALUES (%s, now(), 'complete') RETURNING id", (bid,)).fetchone()["id"]
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,goal_alignment,"
                 "mentions_contested,surfaces_owned,failed) VALUES "
                 "(%s,%s,'chatgpt','Is Acme legit?','Yes, licensed.',0.7,false,true,false)", (rid, bid))
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,goal_alignment,"
                 "mentions_contested,surfaces_owned,failed) VALUES "
                 "(%s,%s,'gemini','Is Acme a scam?','Some forums say MLM.',-0.4,true,false,false)", (rid, bid))
    conn.execute("INSERT INTO site_audits (business_id, run_id, summary) VALUES (%s,%s,%s)",
                 (bid, rid, json.dumps({"pages_crawled": 12, "schema_gaps": ["FAQPage"]})))
    conn.execute("INSERT INTO gap_models (business_id, run_id, model) VALUES (%s,%s,%s)",
                 (bid, rid, json.dumps({"summary": "Needs more owned content",
                                        "weak_queries": [{"prompt": "Is Acme a scam?"}]})))
    conn.commit()
    return bid, rid


@requires_db
def test_audit_runs_and_answers(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    bid, rid = _seed_data(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        runs = c.get(f"/businesses/{bid}/audit-runs", headers=h)
        assert runs.status_code == 200
        run = runs.json()[0]
        assert run["id"] == rid and run["status"] == "complete" and run["n_answers"] == 2
        assert run["goal_alignment"] is not None        # AVG over the two answers
        assert 0.0 < run["contested_rate"] < 1.0        # 1 of 2 contested

        ans = c.get(f"/businesses/{bid}/audit-runs/{rid}/answers", headers=h)
        assert ans.status_code == 200 and len(ans.json()) == 2

        # filter by engine
        only = c.get(f"/businesses/{bid}/audit-runs/{rid}/answers?engine=gemini", headers=h)
        assert only.status_code == 200 and len(only.json()) == 1
        assert only.json()[0]["mentions_contested"] is True


@requires_db
def test_site_audit_and_gap_model(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    bid, _ = _seed_data(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        site = c.get(f"/businesses/{bid}/site-audit", headers=h)
        assert site.status_code == 200 and site.json()["summary"]["pages_crawled"] == 12
        gap = c.get(f"/businesses/{bid}/gap-model", headers=h)
        assert gap.status_code == 200 and "Needs more owned content" in gap.json()["model"]["summary"]
        ba = c.get(f"/businesses/{bid}/answers/before-after", headers=h)
        assert ba.status_code == 200 and isinstance(ba.json(), list)


@requires_db
def test_reads_are_tenancy_guarded(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    bid, rid = _seed_data(conn)
    # a client with NO access to this business
    conn.execute("INSERT INTO users (email,password_hash,role) VALUES ('c@example.com',%s,'client')",
                 (auth.hash_password("pw12345678"),))
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c, 'c@example.com')}"}
        assert c.get(f"/businesses/{bid}/audit-runs", headers=h).status_code == 403
        assert c.get(f"/businesses/{bid}/site-audit", headers=h).status_code == 403
        assert c.get(f"/businesses/{bid}/gap-model", headers=h).status_code == 403
