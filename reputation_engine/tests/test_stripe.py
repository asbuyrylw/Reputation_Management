"""Phase 2c — Stripe billing (Checkout / Portal / signature-verified idempotent webhook).

The stripe SDK is fully mocked: no network, and the 'stripe' package need not be installed.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

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


def _owner(conn, org_id, email="owner@org.com"):
    from rep_engine.api import auth
    conn.execute("INSERT INTO users (email, password_hash, role, org_id, org_role) "
                 "VALUES (%s,%s,'client',%s,'owner')", (email, auth.hash_password("pw12345678"), org_id))
    conn.commit()


def _token(c, email):
    return c.post("/auth/login", json={"email": email, "password": "pw12345678"}).json()["access_token"]


def _fake_stripe(event=None, raise_sig=False, captured=None):
    cap = captured if captured is not None else []

    def session_create(**kw):
        cap.append(kw)
        return SimpleNamespace(url="https://checkout.stripe/test", id="cs_test_123")

    def portal_create(**kw):
        return SimpleNamespace(url="https://portal.stripe/test")

    def construct(payload, sig, secret):
        if raise_sig:
            raise ValueError("invalid signature")
        return event

    return SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=session_create)),
        billing_portal=SimpleNamespace(Session=SimpleNamespace(create=portal_create)),
        Webhook=SimpleNamespace(construct_event=construct),
    )


def _enable_stripe(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")


@requires_db
def test_checkout_creates_session(fresh_schema, monkeypatch):
    from rep_engine import stripe_gateway as sg
    conn = fresh_schema
    org = conn.execute("INSERT INTO organizations (name) VALUES ('Org') RETURNING id").fetchone()["id"]
    _owner(conn, org)
    conn.commit()
    _enable_stripe(monkeypatch)
    cap: list = []
    monkeypatch.setattr(sg, "_stripe", lambda: _fake_stripe(captured=cap))
    with _client() as c:
        # plans are seeded on startup; map the starter price (as STRIPE_PRICE_STARTER would)
        conn.execute("UPDATE plan_catalog SET stripe_price_id='price_starter' WHERE code='starter'")
        conn.commit()
        h = {"Authorization": f"Bearer {_token(c, 'owner@org.com')}"}
        r = c.post("/billing/checkout", headers=h, json={"plan_code": "starter"})
        assert r.status_code == 200
        assert r.json()["url"].startswith("https://checkout.stripe/")
        assert cap[0]["line_items"][0]["price"] == "price_starter"        # correct price wired
        assert cap[0]["metadata"]["org_id"] == str(org)                   # org tagged for the webhook


@requires_db
def test_checkout_503_when_disabled(fresh_schema, monkeypatch):
    conn = fresh_schema
    org = conn.execute("INSERT INTO organizations (name) VALUES ('Org') RETURNING id").fetchone()["id"]
    _owner(conn, org)
    conn.commit()
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)   # billing not configured
    with _client() as c:
        h = {"Authorization": f"Bearer {_token(c, 'owner@org.com')}"}
        assert c.post("/billing/checkout", headers=h, json={"plan_code": "starter"}).status_code == 503


@requires_db
def test_webhook_activates_subscription(fresh_schema, monkeypatch):
    from rep_engine import stripe_gateway as sg
    conn = fresh_schema
    _admin(conn)
    org = conn.execute("INSERT INTO organizations (name) VALUES ('Org') RETURNING id").fetchone()["id"]
    conn.commit()
    _enable_stripe(monkeypatch)
    event = {"id": "evt_1", "type": "checkout.session.completed",
             "data": {"object": {"metadata": {"org_id": str(org), "plan_code": "growth"},
                                 "customer": "cus_1", "subscription": "sub_1"}}}
    monkeypatch.setattr(sg, "_stripe", lambda: _fake_stripe(event=event))
    with _client() as c:
        r = c.post("/billing/webhook", headers={"stripe-signature": "t=1,v1=x"}, content=b"{}")
        assert r.status_code == 200 and r.json()["received"] is True
    sub = conn.execute("SELECT status, plan_code, stripe_customer_id, stripe_subscription_id "
                       "FROM subscriptions WHERE org_id=%s", (org,)).fetchone()
    assert sub["status"] == "active" and sub["plan_code"] == "growth"
    assert sub["stripe_customer_id"] == "cus_1" and sub["stripe_subscription_id"] == "sub_1"


@requires_db
def test_webhook_bad_signature_400(fresh_schema, monkeypatch):
    from rep_engine import stripe_gateway as sg
    fresh_schema
    _enable_stripe(monkeypatch)
    monkeypatch.setattr(sg, "_stripe", lambda: _fake_stripe(raise_sig=True))
    with _client() as c:
        r = c.post("/billing/webhook", headers={"stripe-signature": "bad"}, content=b"{}")
        assert r.status_code == 400


@requires_db
def test_webhook_is_idempotent(fresh_schema, monkeypatch):
    from rep_engine import stripe_gateway as sg
    conn = fresh_schema
    org = conn.execute("INSERT INTO organizations (name) VALUES ('Org') RETURNING id").fetchone()["id"]
    conn.commit()
    _enable_stripe(monkeypatch)
    event = {"id": "evt_dupe", "type": "customer.subscription.updated",
             "data": {"object": {"metadata": {"org_id": str(org), "plan_code": "pro"},
                                 "status": "active", "id": "sub_9", "customer": "cus_9"}}}
    monkeypatch.setattr(sg, "_stripe", lambda: _fake_stripe(event=event))
    with _client() as c:
        first = c.post("/billing/webhook", headers={"stripe-signature": "x"}, content=b"{}").json()
        second = c.post("/billing/webhook", headers={"stripe-signature": "x"}, content=b"{}").json()
    assert first.get("duplicate") is not True and second.get("duplicate") is True
    n = conn.execute("SELECT COUNT(*) n FROM stripe_events WHERE event_id='evt_dupe'").fetchone()["n"]
    assert n == 1     # the event was recorded exactly once
