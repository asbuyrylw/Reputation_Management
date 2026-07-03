"""Account & data controls: session revocation + GDPR export/delete.
Authenticates via Bearer (CSRF-exempt) for mutating calls."""

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


def _bearer(c, email="admin@example.com", pw="pw12345678"):
    tok = c.post("/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ----------------------------- session revocation -----------------------------
@requires_db
def test_revocation_check_rejects_old_tokens(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    c = _client()
    h = _bearer(c)
    assert c.get("/auth/me", headers=h).status_code == 200
    # revocation stamped AFTER the token's iat -> token is dead
    conn.execute("UPDATE users SET sessions_revoked_at = now() + interval '5 seconds' WHERE email='admin@example.com'")
    conn.commit()
    assert c.get("/auth/me", headers=h).status_code == 401
    # move it into the past -> the same token is valid again
    conn.execute("UPDATE users SET sessions_revoked_at = now() - interval '60 seconds' WHERE email='admin@example.com'")
    conn.commit()
    assert c.get("/auth/me", headers=h).status_code == 200


@requires_db
def test_revoke_endpoint_sets_stamp(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    c = _client()
    r = c.post("/auth/revoke-sessions", headers=_bearer(c))
    assert r.status_code == 200 and r.json()["revoked_all_sessions"] is True
    stamp = conn.execute("SELECT sessions_revoked_at FROM users WHERE email='admin@example.com'").fetchone()
    assert stamp["sessions_revoked_at"] is not None


@requires_db
def test_same_second_relogin_after_revoke_is_accepted(fresh_schema):
    # Regression for the whole-second-iat vs microsecond-revoke boundary: revoking and then
    # immediately re-logging in (same wall-second) must yield a WORKING token, not a dead one.
    conn = fresh_schema
    _admin(conn)
    c = _client()
    assert c.post("/auth/revoke-sessions", headers=_bearer(c)).status_code == 200
    assert c.get("/auth/me", headers=_bearer(c)).status_code == 200


# ----------------------------- GDPR export + delete -----------------------------
@requires_db
def test_export_then_delete_business(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    from rep_engine import competitor as cp
    _admin(conn)
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.commit()
    p.add_prompt(bid, "Is Acme legit?")
    cp.register_competitor(bid, "Rival", "r.com")

    c = _client()
    h = _bearer(c)

    ex = c.get(f"/businesses/{bid}/export", headers=h)
    assert ex.status_code == 200
    body = ex.json()
    assert body["business"]["name"] == "Acme"
    assert len(body["tables"]["custom_prompts"]) == 1
    assert len(body["tables"]["competitors"]) == 1
    # the portability export must NOT leak the co-tenant membership/identity table
    assert "business_access" not in body["tables"]

    d = c.delete(f"/businesses/{bid}", headers=h)
    assert d.status_code == 200 and d.json()["deleted_business"] == bid
    # the business and all its scoped rows are gone
    assert conn.execute("SELECT count(*) n FROM businesses WHERE id=%s", (bid,)).fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) n FROM custom_prompts WHERE business_id=%s", (bid,)).fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) n FROM competitors WHERE business_id=%s", (bid,)).fetchone()["n"] == 0
    # deleting a missing business -> 404
    assert c.delete(f"/businesses/{bid}", headers=h).status_code == 404


@requires_db
def test_delete_requires_admin(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    uid = conn.execute("INSERT INTO users (email, password_hash, role) VALUES ('c@x.com',%s,'client') RETURNING id",
                       (auth.hash_password("pw12345678"),)).fetchone()["id"]
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,'editor')",
                 (uid, bid))
    conn.commit()
    c = _client()
    h = _bearer(c, email="c@x.com")
    # an editor can EXPORT their own business...
    assert c.get(f"/businesses/{bid}/export", headers=h).status_code == 200
    # ...but DELETE is platform-admin only
    assert c.delete(f"/businesses/{bid}", headers=h).status_code == 403
    assert conn.execute("SELECT count(*) n FROM businesses WHERE id=%s", (bid,)).fetchone()["n"] == 1


@requires_db
def test_export_requires_access_to_that_business(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    b1 = conn.execute("INSERT INTO businesses (name) VALUES ('B1') RETURNING id").fetchone()["id"]
    b2 = conn.execute("INSERT INTO businesses (name) VALUES ('B2') RETURNING id").fetchone()["id"]
    uid = conn.execute("INSERT INTO users (email, password_hash, role) VALUES ('c@x.com',%s,'client') RETURNING id",
                       (auth.hash_password("pw12345678"),)).fetchone()["id"]
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) VALUES (%s,%s,'editor')",
                 (uid, b2))
    conn.commit()
    c = _client()
    h = _bearer(c, email="c@x.com")
    # editor of B2 has no access to B1 -> export is 403 and leaks no body
    r = c.get(f"/businesses/{b1}/export", headers=h)
    assert r.status_code == 403
    assert "B1" not in r.text
