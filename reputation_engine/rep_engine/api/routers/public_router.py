"""Public lead-magnet funnel (GTM item 20) -- UNAUTHENTICATED.

A prospect opens /audit/{token}, sees a sanitized AI-reputation teaser (score + band + a few
gaps), and submits their email to get the full report. No auth: the unguessable token is the only
key, and only SANITIZED data is exposed (no answers, no internal plan, no PII). The email-capture
POST has no auth cookie so the CSRF double-submit middleware doesn't challenge it.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

try:
    from ... import public_report as _pr
except ImportError:  # pragma: no cover
    import public_report as _pr  # type: ignore

# Unprefixed (like the OAuth callback) so the URL is a clean /public/...
router = APIRouter(tags=["public"])


@router.get("/public/audit/{token}")
def public_audit(token: str):
    out = _pr.summary_for_token(token)
    if not out.get("found"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link isn't valid.")
    return out


class LeadCapture(BaseModel):
    email: str
    name: str | None = None


@router.post("/public/audit/{token}/lead")
def public_lead(token: str, body: LeadCapture):
    out = _pr.capture_lead(token, body.email, body.name)
    if not out.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, out.get("reason") or "Could not capture")
    return {"ok": True}
