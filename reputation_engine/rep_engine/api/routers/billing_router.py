"""Billing (Phase 2b reads + Phase 2c Stripe): plan catalog, an org's subscription/usage,
and Stripe Checkout / Customer Portal / webhook."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..deps import get_conn, get_current_user, require_org_manager
from ..schemas import CheckoutRequest, PortalRequest

try:
    from ... import billing as _billing
    from ... import stripe_gateway as _stripe
except ImportError:  # pragma: no cover
    import billing as _billing  # type: ignore
    import stripe_gateway as _stripe  # type: ignore

router = APIRouter(tags=["billing"])


def _app_base() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")


@router.get("/plans")
def list_plans(_: dict = Depends(get_current_user), conn=Depends(get_conn)):
    """The subscription plan catalog (any authenticated user can see what's offered)."""
    return [dict(r) for r in _billing.list_plans(conn)]


@router.get("/orgs/me/subscription")
def my_subscription(user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    """The current user's organization: plan, subscription status, and this month's usage."""
    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not a member of an organization")
    return _billing.usage_summary(conn, org_id)


# --- Stripe Checkout / Customer Portal / webhook (Phase 2c) ---
@router.post("/billing/checkout")
def checkout(body: CheckoutRequest, user: dict = Depends(require_org_manager),
             conn=Depends(get_conn)):
    """Create a Stripe Checkout Session for the caller's org to subscribe to a plan."""
    if not _stripe.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured")
    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are not a member of an organization")
    base = _app_base()
    try:
        return _stripe.create_checkout_session(
            conn, org_id, body.plan_code,
            success_url=body.success_url or f"{base}/settings?billing=success",
            cancel_url=body.cancel_url or f"{base}/settings?billing=cancel",
            email=user.get("email"),
        )
    except RuntimeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/billing/portal")
def portal(body: PortalRequest, user: dict = Depends(require_org_manager),
           conn=Depends(get_conn)):
    """Create a Stripe Billing Portal session so the org can manage its subscription/card."""
    if not _stripe.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured")
    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are not a member of an organization")
    try:
        return _stripe.create_portal_session(
            conn, org_id, return_url=body.return_url or f"{_app_base()}/settings")
    except RuntimeError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook: signature-verified + idempotent. No auth (Stripe is server-to-server;
    authenticity comes from the signature). Reads the RAW body for signature verification."""
    if not _stripe.enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        return _stripe.handle_webhook(payload, sig)
    except ValueError as e:                       # bad signature
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except RuntimeError as e:                      # misconfiguration (no webhook secret)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
