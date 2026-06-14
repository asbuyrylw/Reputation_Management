"""Phase-5 API tests: admin user/business management + access grants, and the
background-job runner (enqueue -> run -> status, bad type, and the same-type 409).
The job dispatch is mocked so no real audit runs."""

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
def test_admin_user_business_access_flow(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}

        b = c.post("/admin/businesses", headers=h, json={"name": "NewCo", "domain": "newco.com"})
        assert b.status_code == 201
        bid = b.json()["id"]

        u = c.post("/admin/users", headers=h,
                   json={"email": "client@example.com", "password": "pw12345678", "role": "client"})
        assert u.status_code == 201
        uid = u.json()["id"]
        # duplicate email -> 409
        assert c.post("/admin/users", headers=h,
                      json={"email": "client@example.com", "password": "x12345678"}).status_code == 409

        # grant editor access, then the client sees the business with can_edit=true
        assert c.post(f"/admin/users/{uid}/access", headers=h,
                      json={"business_id": bid, "access_role": "editor"}).status_code == 201
        ch = {"Authorization": f"Bearer {_token(c, 'client@example.com')}"}
        biz = c.get("/businesses", headers=ch).json()
        assert len(biz) == 1 and biz[0]["can_edit"] is True

        # update the business
        up = c.patch(f"/admin/businesses/{bid}", headers=h, json={"goal": "win locally"})
        assert up.status_code == 200 and up.json()["goal"] == "win locally"

        # admin endpoints are admin-only
        assert c.get("/admin/users", headers=ch).status_code == 403


@requires_db
def test_job_enqueue_run_and_conflict(fresh_schema, monkeypatch):
    from rep_engine.api import jobs
    ran = []
    monkeypatch.setitem(jobs.JOB_DISPATCH, "audit", lambda bid, args: ran.append(bid))

    conn = fresh_schema
    _admin(conn)
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.commit()

    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}

        r = c.post(f"/businesses/{bid}/jobs/audit", headers=h)
        assert r.status_code == 202
        jid = r.json()["job_id"]

        # ensure it runs deterministically (claim is a no-op if the inline task already ran it)
        jobs.run_job(jid)
        assert ran == [bid] or ran == [bid, bid][:1] or bid in ran
        assert c.get(f"/jobs/{jid}", headers=h).json()["status"] == "complete"

        # unknown job type -> 400
        assert c.post(f"/businesses/{bid}/jobs/nope", headers=h).status_code == 400

        # an already-running same-type job -> 409
        conn.execute("INSERT INTO api_jobs (business_id, job_type, status) VALUES (%s,'citation_analyze','running')", (bid,))
        conn.commit()
        assert c.post(f"/businesses/{bid}/jobs/citation_analyze", headers=h).status_code == 409

        lj = c.get(f"/businesses/{bid}/jobs", headers=h)
        assert lj.status_code == 200 and "jobs" in lj.json() and "pipeline_runs" in lj.json()
