"""Phase-1 API tenancy tests: admins see all businesses, clients only their own,
cross-tenant access is 403, and clients don't see internal cost-of-goods."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _user(conn, email, role="client"):
    from rep_engine.api import auth
    return conn.execute(
        "INSERT INTO users (email, password_hash, role) VALUES (%s,%s,%s) RETURNING id",
        (email, auth.hash_password("pw12345678"), role),
    ).fetchone()["id"]


def _biz(conn, name):
    return conn.execute(
        "INSERT INTO businesses (name, domain) VALUES (%s,%s) RETURNING id",
        (name, name.lower() + ".com"),
    ).fetchone()["id"]


def _token(client, email):
    return client.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


@requires_db
def test_admin_all_client_scoped_and_cross_tenant_403(fresh_schema):
    conn = fresh_schema
    b1, b2 = _biz(conn, "Alpha"), _biz(conn, "Beta")
    _user(conn, "admin@example.com", "admin")
    cid = _user(conn, "client@example.com", "client")
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) "
                 "VALUES (%s,%s,'viewer')", (cid, b1))
    conn.commit()

    with _client() as c:
        ah = {"Authorization": f"Bearer {_token(c, 'admin@example.com')}"}
        ch = {"Authorization": f"Bearer {_token(c, 'client@example.com')}"}

        # list scoping
        assert {b["id"] for b in c.get("/businesses", headers=ah).json()} == {b1, b2}
        assert {b["id"] for b in c.get("/businesses", headers=ch).json()} == {b1}

        # client: own business OK, other business 403 (detail + dashboard)
        assert c.get(f"/businesses/{b1}", headers=ch).status_code == 200
        assert c.get(f"/businesses/{b2}", headers=ch).status_code == 403
        assert c.get(f"/businesses/{b2}/dashboard", headers=ch).status_code == 403

        # admin reaches everything
        assert c.get(f"/businesses/{b2}", headers=ah).status_code == 200

        # client dashboard omits month_cost; admin dashboard includes it
        cdash = c.get(f"/businesses/{b1}/dashboard", headers=ch)
        assert cdash.status_code == 200 and "month_cost" not in cdash.json()
        adash = c.get(f"/businesses/{b1}/dashboard", headers=ah)
        assert adash.status_code == 200 and "month_cost" in adash.json()


@requires_db
def test_unauthenticated_is_401(fresh_schema):
    conn = fresh_schema
    b1 = _biz(conn, "Alpha")
    with _client() as c:
        assert c.get("/businesses").status_code == 401
        assert c.get(f"/businesses/{b1}").status_code == 401
