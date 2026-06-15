"""
Stripe billing gateway (Phase 2c)
=================================
Checkout + Customer Portal + a signature-verified, idempotent webhook that drives org
subscription statuses (Phase 2b). The stripe SDK is imported LAZILY and the whole module
degrades gracefully when STRIPE_SECRET_KEY is unset or the package isn't installed, so the
app runs fine without Stripe configured (endpoints return a clear 503).

Stripe event -> our subscription status:
  checkout.session.completed                         -> active (+ store stripe customer/sub ids)
  customer.subscription.created/updated              -> mirror Stripe status
  customer.subscription.deleted                      -> canceled
  invoice.payment_failed                             -> past_due
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    from .db import db
    from . import billing as _billing
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import billing as _billing  # type: ignore

log = logging.getLogger("stripe_gateway")

# Stripe subscription.status -> our status vocabulary.
_STATUS_MAP = {
    "active": "active", "trialing": "trialing", "past_due": "past_due",
    "canceled": "canceled", "unpaid": "past_due", "incomplete": "past_due",
    "incomplete_expired": "canceled", "paused": "past_due",
}


def enabled() -> bool:
    """True when Stripe is configured (a secret key is present)."""
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def _stripe():
    """Return the configured stripe SDK module, or raise a clear error if unavailable."""
    if not enabled():
        raise RuntimeError("Stripe is not configured (set STRIPE_SECRET_KEY).")
    try:
        import stripe  # lazy: the app/tests run without the package installed
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("the 'stripe' package is not installed") from e
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    return stripe


def _price_id(conn, plan_code: str) -> Optional[str]:
    row = conn.execute("SELECT stripe_price_id FROM plan_catalog WHERE code=%s",
                       (plan_code,)).fetchone()
    return row["stripe_price_id"] if row else None


def _org_customer_id(conn, org_id: int) -> Optional[str]:
    sub = _billing.get_subscription(conn, org_id)
    return sub["stripe_customer_id"] if sub else None


# ---------------------------------------------------------------------------
# Checkout + Customer Portal
# ---------------------------------------------------------------------------
def create_checkout_session(conn, org_id: int, plan_code: str, *, success_url: str,
                            cancel_url: str, email: Optional[str] = None) -> dict:
    """Create a Stripe Checkout Session for an org to subscribe to a plan."""
    stripe = _stripe()
    price = _price_id(conn, plan_code)
    if not price:
        raise RuntimeError(
            f"plan '{plan_code}' has no Stripe price configured (set STRIPE_PRICE_{plan_code.upper()}).")
    params = {
        "mode": "subscription",
        "line_items": [{"price": price, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(org_id),
        "metadata": {"org_id": str(org_id), "plan_code": plan_code},
        "subscription_data": {"metadata": {"org_id": str(org_id), "plan_code": plan_code}},
    }
    customer = _org_customer_id(conn, org_id)
    if customer:
        params["customer"] = customer
    elif email:
        params["customer_email"] = email
    session = stripe.checkout.Session.create(**params)
    return {"url": session.url, "id": session.id}


def create_portal_session(conn, org_id: int, *, return_url: str) -> dict:
    """Create a Stripe Billing Portal session so an org can manage its subscription/card."""
    stripe = _stripe()
    customer = _org_customer_id(conn, org_id)
    if not customer:
        raise RuntimeError("no Stripe customer for this organization yet (subscribe via checkout first).")
    session = stripe.billing_portal.Session.create(customer=customer, return_url=return_url)
    return {"url": session.url}


# ---------------------------------------------------------------------------
# Webhook (signature-verified + idempotent)
# ---------------------------------------------------------------------------
def handle_webhook(payload: bytes, sig_header: Optional[str]) -> dict:
    """Verify the Stripe signature, dedupe by event id, and apply the event. Raises
    ValueError on a bad signature (caller returns 400)."""
    stripe = _stripe()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except Exception as e:  # signature failure / malformed payload
        raise ValueError(f"invalid Stripe signature: {e}") from e
    event_id, etype = event["id"], event["type"]
    with db() as conn:
        # idempotency: claim the event id; if it's already recorded, skip applying it.
        claimed = conn.execute(
            "INSERT INTO stripe_events (event_id, type) VALUES (%s,%s) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING event_id", (event_id, etype),
        ).fetchone()
        if not claimed:
            conn.commit()
            return {"received": True, "duplicate": True}
        try:
            _apply_event(conn, event)
        except Exception:  # noqa: BLE001 -- never 500 a webhook; keep the dedupe row, log, ack
            log.exception("stripe webhook apply failed for %s (%s)", event_id, etype)
        conn.commit()
    return {"received": True, "type": etype}


def _apply_event(conn, event) -> None:
    etype = event["type"]
    obj = event["data"]["object"]
    if etype == "checkout.session.completed":
        org_id = _org_from(obj)
        plan = (obj.get("metadata") or {}).get("plan_code")
        if org_id and plan:
            _billing.subscribe(conn, org_id, plan, status="active")
            _attach_ids(conn, org_id, obj.get("customer"), obj.get("subscription"))
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        org_id = _org_from(obj)
        if org_id:
            status = _STATUS_MAP.get(obj.get("status"), "past_due")
            plan = (obj.get("metadata") or {}).get("plan_code")
            if plan:
                _billing.subscribe(conn, org_id, plan, status=status)
            else:
                conn.execute("UPDATE subscriptions SET status=%s, updated_at=now() WHERE org_id=%s",
                             (status, org_id))
            _attach_ids(conn, org_id, obj.get("customer"), obj.get("id"))
    elif etype == "customer.subscription.deleted":
        org_id = _org_from(obj)
        if org_id:
            conn.execute("UPDATE subscriptions SET status='canceled', updated_at=now() WHERE org_id=%s",
                         (org_id,))
    elif etype == "invoice.payment_failed":
        cust = obj.get("customer")
        if cust:
            conn.execute("UPDATE subscriptions SET status='past_due', updated_at=now() "
                         "WHERE stripe_customer_id=%s", (cust,))


def _org_from(obj) -> Optional[int]:
    md = obj.get("metadata") or {}
    val = md.get("org_id") or obj.get("client_reference_id")
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _attach_ids(conn, org_id, customer_id, subscription_id) -> None:
    conn.execute(
        "UPDATE subscriptions SET stripe_customer_id=COALESCE(%s, stripe_customer_id), "
        "stripe_subscription_id=COALESCE(%s, stripe_subscription_id), updated_at=now() "
        "WHERE org_id=%s",
        (customer_id, subscription_id, org_id),
    )
