"""Deploy-hardening tests: login rate-limit, httpOnly cookie auth, and audit logging."""

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


def test_rate_limit_function():
    from rep_engine.api import ratelimit
    ratelimit.reset()
    results = [ratelimit.rate_check("1.2.3.4") for _ in range(ratelimit.MAX_ATTEMPTS + 2)]
    assert all(results[: ratelimit.MAX_ATTEMPTS])              # first MAX allowed
    assert results[ratelimit.MAX_ATTEMPTS] is False            # the next is blocked
    assert ratelimit.rate_check("9.9.9.9") is True             # a different key is unaffected
    ratelimit.reset()


@requires_db
def test_login_sets_cookie_and_cookie_authenticates(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        r = c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"})
        assert r.status_code == 200 and "rc_token" in r.cookies   # httpOnly cookie set
        # the TestClient stores the cookie; a request WITHOUT a bearer authenticates via it
        me = c.get("/auth/me")
        assert me.status_code == 200 and me.json()["email"] == "admin@example.com"
        assert c.post("/auth/logout").status_code == 200


@requires_db
def test_writes_are_audit_logged(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        tok = c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"}).json()["access_token"]
        c.post("/admin/businesses", headers={"Authorization": f"Bearer {tok}"}, json={"name": "X"})
    rows = conn.execute("SELECT user_id, method, path, status_code FROM audit_log ORDER BY id").fetchall()
    paths = [r["path"] for r in rows]
    assert "/auth/login" in paths and "/admin/businesses" in paths
    biz = next(r for r in rows if r["path"] == "/admin/businesses")
    assert biz["status_code"] == 201 and biz["user_id"] == 1   # the admin's action, attributed
