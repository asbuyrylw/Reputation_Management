"""Phase-1 API auth tests: password hashing, login -> JWT, /auth/me.

Sets JWT_SECRET at import (before the FastAPI app is built). DB-backed tests reuse
the conftest fresh_schema fixture (alembic upgrade head + truncate)."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _mk_user(conn, email, password, role="admin"):
    from rep_engine.api import auth
    conn.execute("INSERT INTO users (email, password_hash, role) VALUES (%s,%s,%s)",
                 (email, auth.hash_password(password), role))
    conn.commit()


def test_password_hash_roundtrip():
    from rep_engine.api import auth
    h = auth.hash_password("s3cret-pw")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_password("s3cret-pw", h)
    assert not auth.verify_password("wrong", h)
    assert not auth.verify_password("s3cret-pw", "malformed$hash")   # never raises


@requires_db
def test_login_issues_token_and_me(fresh_schema):
    conn = fresh_schema
    _mk_user(conn, "admin@example.com", "pw12345678", "admin")
    with _client() as c:
        r = c.post("/auth/login", json={"email": "admin@example.com", "password": "pw12345678"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
        tok = body["access_token"]
        me = c.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200
        assert me.json()["email"] == "admin@example.com"
        assert me.json()["business_ids"] is None       # admin => all businesses


@requires_db
def test_login_rejects_bad_password(fresh_schema):
    conn = fresh_schema
    _mk_user(conn, "admin@example.com", "pw12345678", "admin")
    with _client() as c:
        r = c.post("/auth/login", json={"email": "admin@example.com", "password": "nope"})
        assert r.status_code == 401
        # case-insensitive email still authenticates
        ok = c.post("/auth/login", json={"email": "ADMIN@example.com", "password": "pw12345678"})
        assert ok.status_code == 200


@requires_db
def test_me_requires_valid_token(fresh_schema):
    with _client() as c:
        assert c.get("/auth/me").status_code == 401
        assert c.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_health_endpoints():
    with _client() as c:
        assert c.get("/livez").status_code == 200
        r = c.get("/readyz")
        assert r.status_code in (200, 503)
        assert "checks" in r.json()


@requires_db
def test_change_password(fresh_schema):
    conn = fresh_schema
    _mk_user(conn, "u@example.com", "OldPass123!", "client")
    with _client() as c:
        tok = c.post("/auth/login", json={"email": "u@example.com", "password": "OldPass123!"}).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        # wrong current password -> 403
        assert c.post("/auth/change-password", json={"current_password": "wrong", "new_password": "Brand-New99"}, headers=h).status_code == 403
        # weak new password -> 400
        assert c.post("/auth/change-password", json={"current_password": "OldPass123!", "new_password": "short"}, headers=h).status_code == 400
        # valid change -> 200, and the new password logs in
        ok = c.post("/auth/change-password", json={"current_password": "OldPass123!", "new_password": "Brand-New99"}, headers=h)
        assert ok.status_code == 200, ok.text
        assert c.post("/auth/login", json={"email": "u@example.com", "password": "Brand-New99"}).status_code == 200
        assert c.post("/auth/login", json={"email": "u@example.com", "password": "OldPass123!"}).status_code == 401
