"""Phase 2d — onboarding: teammate invites, accept-invite, forgot/reset password, and the
Team Unstoppable pilot provisioner. Email is disabled (logged, not sent) in tests."""

from __future__ import annotations

import os
import re

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


def _token(c, email="admin@example.com", pw="pw12345678"):
    return c.post("/auth/login", json={"email": email, "password": pw}).json()["access_token"]


def _tok_from(text):
    return re.search(r"token=([^&\s]+)", text).group(1)


@requires_db
def test_invite_accept_and_login(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        org = c.post("/admin/organizations", headers=h, json={"name": "O"}).json()["id"]
        inv = c.post("/auth/invite", headers=h,
                     json={"email": "new@org.com", "org_id": org, "org_role": "member"})
        assert inv.status_code == 201
        link = inv.json()["invite_link"]
        assert link                                   # email disabled -> link returned
        tok = _tok_from(link)
        # inactive until accepted -> cannot sign in
        assert c.post("/auth/login", json={"email": "new@org.com", "password": "newpass123"}).status_code == 401
        assert c.post("/auth/accept-invite", json={"token": tok, "password": "newpass123"}).status_code == 200
        # now active -> can sign in
        assert c.post("/auth/login", json={"email": "new@org.com", "password": "newpass123"}).status_code == 200
        # the invite token is single-use
        assert c.post("/auth/accept-invite", json={"token": tok, "password": "other123"}).status_code == 400


@requires_db
def test_org_owner_can_invite_member_cannot(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    org = conn.execute("INSERT INTO organizations (name) VALUES ('O') RETURNING id").fetchone()["id"]
    for email, role in [("owner@o.com", "owner"), ("mem@o.com", "member")]:
        conn.execute("INSERT INTO users (email, password_hash, role, is_active, org_id, org_role) "
                     "VALUES (%s,%s,'client',true,%s,%s)",
                     (email, auth.hash_password("pw12345678"), org, role))
    conn.commit()
    with _client() as c:
        oh = {"Authorization": f"Bearer {_token(c, 'owner@o.com')}"}
        assert c.post("/auth/invite", headers=oh, json={"email": "t1@o.com"}).status_code == 201
        mh = {"Authorization": f"Bearer {_token(c, 'mem@o.com')}"}
        assert c.post("/auth/invite", headers=mh, json={"email": "t2@o.com"}).status_code == 403


@requires_db
def test_forgot_and_reset_password(fresh_schema, monkeypatch):
    from rep_engine import email_service
    from rep_engine.api import auth
    conn = fresh_schema
    conn.execute("INSERT INTO users (email, password_hash, role, is_active) VALUES ('u@x.com',%s,'client',true)",
                 (auth.hash_password("oldpass123"),))
    conn.commit()
    sent = []
    monkeypatch.setattr(email_service, "send_email",
                        lambda to, subj, text, html=None: sent.append(text) or False)
    with _client() as c:
        assert c.post("/auth/forgot-password", json={"email": "u@x.com"}).status_code == 200
        # an unknown email returns the SAME ok (no account enumeration)
        assert c.post("/auth/forgot-password", json={"email": "nope@x.com"}).status_code == 200
        assert len(sent) == 1                          # only the real account got mail
        tok = _tok_from(sent[0])
        assert c.post("/auth/reset-password", json={"token": tok, "password": "newpass123"}).status_code == 200
        assert c.post("/auth/login", json={"email": "u@x.com", "password": "newpass123"}).status_code == 200
        assert c.post("/auth/login", json={"email": "u@x.com", "password": "oldpass123"}).status_code == 401


@requires_db
def test_reset_password_rejects_short_password(fresh_schema):
    conn = fresh_schema
    from rep_engine.api import auth
    uid = conn.execute("INSERT INTO users (email, password_hash, role, is_active) "
                       "VALUES ('s@x.com',%s,'client',true) RETURNING id",
                       (auth.hash_password("oldpass123"),)).fetchone()["id"]
    raw = auth.issue_action_token(conn, uid, "reset", 2)
    conn.commit()
    with _client() as c:
        assert c.post("/auth/reset-password", json={"token": raw, "password": "short"}).status_code == 400


@requires_db
def test_provision_pilot(fresh_schema):
    conn = fresh_schema
    from rep_engine import provision_pilot
    out = provision_pilot.provision("owner@teamunstoppable.com", owner_name="Owner")
    assert out["org_id"] and out["business_id"] and out["invite_link"]
    biz = conn.execute("SELECT name, domain, contested_terms, org_id FROM businesses WHERE id=%s",
                       (out["business_id"],)).fetchone()
    assert biz["domain"] == "teamunstoppable.com" and "MLM" in biz["contested_terms"]
    assert biz["org_id"] == out["org_id"]
    # idempotent: re-running reuses the org + business and doesn't duplicate
    out2 = provision_pilot.provision("owner@teamunstoppable.com")
    assert out2["org_id"] == out["org_id"] and out2["business_id"] == out["business_id"]
    n = conn.execute("SELECT COUNT(*) n FROM organizations WHERE name='Team Unstoppable'").fetchone()["n"]
    assert n == 1
