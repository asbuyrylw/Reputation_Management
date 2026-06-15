"""Billing reads (Phase 2b): the public plan catalog + an org's own subscription/usage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_conn, get_current_user

try:
    from ... import billing as _billing
except ImportError:  # pragma: no cover
    import billing as _billing  # type: ignore

router = APIRouter(tags=["billing"])


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
