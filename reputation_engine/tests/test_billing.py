"""Phase 2b — COGS model, plan catalog, subscriptions, and the quota/entitlement gate.

The job dispatch is mocked so no real audit runs (zero spend). The gate is backward-compatible:
a business with no org, or an org with no subscription, is unmetered.
"""

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


# ---------------------------------------------------------------------------
# COGS model (pure)
# ---------------------------------------------------------------------------
def test_cogs_monotonic_and_tiers():
    from rep_engine import cogs
    base = cogs.audit_cogs(battery=10, engines=2, samples=1)
    assert cogs.audit_cogs(battery=20, engines=2, samples=1) > base   # more battery
    assert cogs.audit_cogs(battery=10, engines=4, samples=1) > base   # more engines
    assert cogs.audit_cogs(battery=10, engines=2, samples=3) > base   # more samples
    tiers = cogs.propose_tiers(target_margin=0.80)
    assert {t["code"] for t in tiers} == {"starter", "growth", "pro", "agency"}
    for t in tiers:
        # price clears the gross-margin floor (rounded up to a marketable number)
        assert t["price_usd_month"] >= t["price_floor"] - 1 and t["price_usd_month"] > 0
        # a plan's price should comfortably exceed its monthly COGS
        assert t["price_usd_month"] > t["monthly_cogs"]


# ---------------------------------------------------------------------------
# subscriptions
# ---------------------------------------------------------------------------
@requires_db
def test_seed_subscribe_and_is_active(fresh_schema):
    conn = fresh_schema
    from rep_engine import billing
    billing.seed_plans()
    assert len(billing.list_plans(conn)) == 4
    oid = conn.execute("INSERT INTO organizations (name) VALUES ('O') RETURNING id").fetchone()["id"]
    conn.commit()
    sub = billing.subscribe(conn, oid, "starter", status="trialing")
    conn.commit()
    assert sub["plan_code"] == "starter" and sub["trial_end"] is not None
    assert billing.is_active(sub) is True
    canceled = billing.subscribe(conn, oid, "starter", status="canceled")
    conn.commit()
    assert billing.is_active(canceled) is False


# ---------------------------------------------------------------------------
# the gate (via the trigger endpoint)
# ---------------------------------------------------------------------------
@requires_db
def test_quota_and_subscription_gate(fresh_schema, monkeypatch):
    from rep_engine.api import jobs
    monkeypatch.setitem(jobs.JOB_DISPATCH, "audit", lambda bid, args: None)  # no real audit
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        oid = c.post("/admin/organizations", headers=h, json={"name": "Org"}).json()["id"]
        bid = c.post("/admin/businesses", headers=h, json={"name": "Biz", "org_id": oid}).json()["id"]
        # starter = 4 audits/mo, active
        assert c.post(f"/admin/organizations/{oid}/subscription", headers=h,
                      json={"plan_code": "starter", "status": "active"}).status_code == 201

        # under quota -> allowed
        assert c.post(f"/businesses/{bid}/jobs/audit", headers=h).status_code == 202

        # fill the monthly audit quota (4) with audit_runs this month
        for _ in range(4):
            conn.execute("INSERT INTO audit_runs (business_id, started_at, status) "
                         "VALUES (%s, now(), 'complete')", (bid,))
        conn.commit()
        # over quota -> 429 (the gate short-circuits before enqueue)
        assert c.post(f"/businesses/{bid}/jobs/audit", headers=h).status_code == 429

        # cancel the subscription -> any spending trigger is 402
        c.post(f"/admin/organizations/{oid}/subscription", headers=h,
               json={"plan_code": "starter", "status": "canceled"})
        assert c.post(f"/businesses/{bid}/jobs/citation_analyze", headers=h).status_code == 402


@requires_db
def test_legacy_business_without_org_is_unmetered(fresh_schema, monkeypatch):
    from rep_engine.api import jobs
    monkeypatch.setitem(jobs.JOB_DISPATCH, "audit", lambda bid, args: None)
    conn = fresh_schema
    _admin(conn)
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Legacy') RETURNING id").fetchone()["id"]
    conn.commit()
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        # no org / no subscription => unmetered, trigger allowed
        assert c.post(f"/businesses/{bid}/jobs/audit", headers=h).status_code == 202


# ---------------------------------------------------------------------------
# billing read endpoints
# ---------------------------------------------------------------------------
@requires_db
def test_plans_and_my_subscription_endpoints(fresh_schema):
    conn = fresh_schema
    _admin(conn)
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c)}"}
        plans = c.get("/plans", headers=h).json()
        assert {p["code"] for p in plans} == {"starter", "growth", "pro", "agency"}

        oid = c.post("/admin/organizations", headers=h, json={"name": "O"}).json()["id"]
        c.post(f"/admin/organizations/{oid}/subscription", headers=h, json={"plan_code": "growth"})
        owner = c.post("/admin/users", headers=h,
                       json={"email": "o@o.com", "password": "pw12345678",
                             "org_id": oid, "org_role": "owner"})
        assert owner.status_code == 201
        oh = {"Authorization": f"Bearer {_token(c, 'o@o.com')}"}
        sub = c.get("/orgs/me/subscription", headers=oh).json()
        assert sub["plan"]["code"] == "growth" and sub["active"] is True
        assert sub["usage"]["audits_this_month"] == 0
