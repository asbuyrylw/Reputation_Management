"""Phase 2a — organizations as the account/tenancy root.

Org owners/admins implicitly access every business in their org; members are limited to
their explicit business_access grants; cross-org access is denied; and legacy users with no
org (NULL) keep working via business_access exactly as before.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-please-change-0123456789abcdef")

from conftest import requires_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client():
    from rep_engine.api.main import app
    return TestClient(app)


def _mk_org(conn, name="Org"):
    return conn.execute("INSERT INTO organizations (name) VALUES (%s) RETURNING id",
                        (name,)).fetchone()["id"]


def _mk_user(conn, email, role="client", org_id=None, org_role="member", pw="pw12345678"):
    from rep_engine.api import auth
    return conn.execute(
        "INSERT INTO users (email, password_hash, role, org_id, org_role) "
        "VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (email, auth.hash_password(pw), role, org_id, org_role),
    ).fetchone()["id"]


def _mk_business(conn, name, org_id=None):
    return conn.execute("INSERT INTO businesses (name, org_id) VALUES (%s,%s) RETURNING id",
                        (name, org_id)).fetchone()["id"]


def _login(c, email, pw="pw12345678"):
    return c.post("/auth/login", json={"email": email, "password": pw}).json()["access_token"]


@requires_db
def test_org_owner_sees_all_org_businesses_without_grants(fresh_schema):
    conn = fresh_schema
    org = _mk_org(conn, "Acme Agency")
    b1 = _mk_business(conn, "Client One", org)
    b2 = _mk_business(conn, "Client Two", org)
    _mk_user(conn, "owner@acme.com", org_id=org, org_role="owner")
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_login(c, 'owner@acme.com')}"}
        lst = c.get("/businesses", headers=h).json()
        assert {b["id"] for b in lst} == {b1, b2}      # all org businesses, no grants needed
        assert all(b["can_edit"] for b in lst)         # owner can edit them
        assert c.get(f"/businesses/{b1}", headers=h).status_code == 200


@requires_db
def test_cross_org_access_is_denied(fresh_schema):
    conn = fresh_schema
    org_a, org_b = _mk_org(conn, "A"), _mk_org(conn, "B")
    b_a = _mk_business(conn, "A-biz", org_a)
    b_b = _mk_business(conn, "B-biz", org_b)
    _mk_user(conn, "a@a.com", org_id=org_a, org_role="owner")
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_login(c, 'a@a.com')}"}
        assert c.get(f"/businesses/{b_a}", headers=h).status_code == 200   # own org
        assert c.get(f"/businesses/{b_b}", headers=h).status_code == 403   # other org denied
        assert {b["id"] for b in c.get("/businesses", headers=h).json()} == {b_a}


@requires_db
def test_org_member_sees_only_granted_businesses(fresh_schema):
    conn = fresh_schema
    org = _mk_org(conn, "Org")
    b1 = _mk_business(conn, "B1", org)
    b2 = _mk_business(conn, "B2", org)
    member = _mk_user(conn, "m@org.com", org_id=org, org_role="member")
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) "
                 "VALUES (%s,%s,'viewer')", (member, b1))
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_login(c, 'm@org.com')}"}
        assert {b["id"] for b in c.get("/businesses", headers=h).json()} == {b1}  # not all org
        assert c.get(f"/businesses/{b1}", headers=h).status_code == 200
        assert c.get(f"/businesses/{b2}", headers=h).status_code == 403  # ungranted -> denied


@requires_db
def test_backward_compat_business_access_without_org(fresh_schema):
    """A legacy client (NULL org) with a business_access grant works unchanged."""
    conn = fresh_schema
    b = _mk_business(conn, "Legacy")       # no org
    u = _mk_user(conn, "legacy@x.com")     # NULL org, member
    conn.execute("INSERT INTO business_access (user_id, business_id, access_role) "
                 "VALUES (%s,%s,'editor')", (u, b))
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_login(c, 'legacy@x.com')}"}
        lst = c.get("/businesses", headers=h).json()
        assert {x["id"] for x in lst} == {b} and lst[0]["can_edit"] is True


@requires_db
def test_admin_org_endpoints_create_and_assign(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    conn.execute("INSERT INTO users (email, password_hash, role) VALUES ('admin@x.com',%s,'admin')",
                 (auth.hash_password("pw12345678"),))
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_login(c, 'admin@x.com')}"}
        org = c.post("/admin/organizations", headers=h, json={"name": "NewCo"})
        assert org.status_code == 201
        oid = org.json()["id"]
        biz = c.post("/admin/businesses", headers=h, json={"name": "NewCo Biz", "org_id": oid})
        assert biz.status_code == 201 and biz.json()["org_id"] == oid
        usr = c.post("/admin/users", headers=h,
                     json={"email": "o@newco.com", "password": "pw12345678",
                           "org_id": oid, "org_role": "owner"})
        assert usr.status_code == 201 and usr.json()["org_role"] == "owner"
        row = next(o for o in c.get("/admin/organizations", headers=h).json() if o["id"] == oid)
        assert row["business_count"] == 1 and row["user_count"] == 1
        # the freshly-created owner immediately sees the org business (no per-business grant)
        h2 = {"Authorization": f"Bearer {_login(c, 'o@newco.com')}"}
        assert {b["id"] for b in c.get("/businesses", headers=h2).json()} == {biz.json()["id"]}
