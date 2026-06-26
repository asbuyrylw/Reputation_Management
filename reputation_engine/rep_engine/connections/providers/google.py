"""
Google OAuth provider -- Business Profile (reviews + local posts), Integrations Phase 1
=======================================================================================
Authorization-code OAuth2 for the Google Business Profile API. Scope `business.manage` covers
read-reviews + reply + local posts. Token endpoints are host-pinned; all I/O via http.request_json.

GBP review-reply additionally requires Google's allowlist approval -- a connection surfaces
`gbp_access='pending'` until an operator marks it approved; the UI/auto-reply path stays disabled
until then.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

try:
    from ... import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

AUTH_HOST = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPES = ["https://www.googleapis.com/auth/business.manage"]


def configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def authorize_url(state: str, redirect_uri: str) -> str:
    """Build the consent URL with minimum scopes + offline access (so we get a refresh token)."""
    q = {
        "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_HOST}?{urlencode(q)}"


def _expires_at(expires_in) -> Optional[datetime]:
    try:
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Trade the auth code for tokens. Returns {ok, access_token, refresh_token, expires_at, scopes}."""
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={
            "code": code,
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "error": res.error or "token exchange failed"}
    d = res.data
    return {"ok": True, "access_token": d.get("access_token"),
            "refresh_token": d.get("refresh_token"),
            "expires_at": _expires_at(d.get("expires_in")),
            "scopes": (d.get("scope") or "").split() or SCOPES}


def refresh(creds: dict) -> dict:
    """Refresh an access token. Returns {ok, access_token, expires_at} or {ok:False, transient?, error}.
    A 4xx invalid_grant is a HARD failure (revoke); a 5xx/network error is transient (retry later)."""
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    rt = creds.get("refresh_token")
    if not rt:
        return {"ok": False, "error": "no refresh token stored"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={
            "refresh_token": rt,
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.ok and isinstance(res.data, dict):
        return {"ok": True, "access_token": res.data.get("access_token"),
                "refresh_token": res.data.get("refresh_token"),  # Google usually omits on refresh
                "expires_at": _expires_at(res.data.get("expires_in"))}
    transient = res.status is None or (res.status or 0) >= 500
    return {"ok": False, "transient": transient, "error": res.error or "refresh failed"}


def revoke(token: Optional[str]) -> None:
    """Best-effort provider-side revoke. Failure is fine -- local revoke is the fail-safe."""
    if not token:
        return
    try:
        _http.request_json("POST", REVOKE_URL, data={"token": token},
                           headers={"Content-Type": "application/x-www-form-urlencoded"},
                           timeout=10, max_retries=1, guard_redirects=True, parse_json=False)
    except Exception:  # noqa: BLE001
        pass
