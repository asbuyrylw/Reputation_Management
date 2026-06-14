"""Phase-4 API tests: rankings (share-of-voice, momentum, root-cause, attribution),
the projection/acceleration/levers reads, incidents + mentions, and the incident
resume safety gate (409 without the durable checkpointer)."""

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


def _token(c, email="admin@example.com"):
    return c.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


@requires_db
def test_rankings_and_sustain_reads(fresh_schema, monkeypatch):
    monkeypatch.delenv("AGENT_CHECKPOINT_PG", raising=False)
    conn = fresh_schema
    _admin(conn)
    bid = conn.execute("INSERT INTO businesses (name, domain, contested_terms) "
                       "VALUES ('Acme','acme.com','MLM') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                       "VALUES (%s, now(), 'complete') RETURNING id", (bid,)).fetchone()["id"]
    conn.execute("INSERT INTO citation_momentum (business_id, domain, run_id, cite_count, share, classification) "
                 "VALUES (%s,'acme.com',%s,5,0.5,'owned')", (bid, rid))
    conn.execute("INSERT INTO citation_momentum (business_id, domain, run_id, cite_count, share, classification) "
                 "VALUES (%s,'ripoffreport.com',%s,3,0.3,'contested')", (bid, rid))
    conn.execute("INSERT INTO root_cause (business_id, model) VALUES (%s,%s)",
                 (bid, json.dumps({"summary": "ripoffreport.com ranks for the contested query"})))
    conn.execute("INSERT INTO attribution (business_id, metric, delta, assets_in_window) "
                 "VALUES (%s,'goal_alignment',0.1,%s)", (bid, json.dumps([])))
    conn.execute("INSERT INTO incidents (business_id, mention_url, severity, status) "
                 "VALUES (%s,'http://r/1','high','pending_human_review')", (bid,))
    conn.execute("INSERT INTO mentions (business_id, source, source_url, sentiment, dedup_hash) "
                 "VALUES (%s,'reddit','http://r/1','negative','hash-1')", (bid,))
    conn.commit()

    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}

        sov = c.get(f"/businesses/{bid}/citations/share-of-voice", headers=h)
        assert sov.status_code == 200
        assert sov.json()["by_classification"]["owned"]["cites"] == 5
        assert sov.json()["by_classification"]["contested"]["cites"] == 3

        assert c.get(f"/businesses/{bid}/citations/momentum", headers=h).status_code == 200
        rc = c.get(f"/businesses/{bid}/root-cause", headers=h)
        assert rc.status_code == 200 and "ripoffreport.com" in rc.json()["model"]["summary"]
        assert c.get(f"/businesses/{bid}/attribution", headers=h).status_code == 200

        # pure projections compute without LLM and return dicts even on thin data
        for path in ("timeline", "acceleration", "learned-levers", "alert"):
            assert c.get(f"/businesses/{bid}/{path}", headers=h).status_code == 200

        inc = c.get(f"/businesses/{bid}/incidents", headers=h)
        assert inc.status_code == 200 and len(inc.json()) == 1
        assert c.get(f"/businesses/{bid}/mentions", headers=h).status_code == 200

        # resuming a human-gated incident without the durable checkpointer must 409
        iid = inc.json()[0]["id"]
        r = c.post(f"/businesses/{bid}/incidents/{iid}/resume", headers=h, json={"approved": True})
        assert r.status_code == 409
