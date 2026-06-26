"""
Google Search Console OAuth provider + Search Analytics client (Wave 1)
=======================================================================
Read-only organic-search data (clicks/impressions/CTR/position). Shares the Google OAuth client
(GOOGLE_OAUTH_CLIENT_ID/SECRET) + token endpoints with providers/google.py but is a SEPARATE
module so the GBP `business.manage` scope and the GSC `webmasters.readonly` scope never entangle.
All I/O via http.request_json(guard_redirects=True), host-pinned to googleapis.com.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, urlencode

try:
    from ... import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

AUTH_HOST = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GSC_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
# webmasters.readonly = read search analytics + list sites; siteverification enables the
# assisted-verification onboarding flow (drop it if verification stays fully manual).
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly",
          "https://www.googleapis.com/auth/siteverification"]


def configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def authorize_url(state: str, redirect_uri: str) -> str:
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
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={"code": code, "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
              "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
              "redirect_uri": redirect_uri, "grant_type": "authorization_code"},
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
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    rt = creds.get("refresh_token")
    if not rt:
        return {"ok": False, "error": "no refresh token stored"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={"refresh_token": rt, "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
              "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
              "grant_type": "refresh_token"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.ok and isinstance(res.data, dict):
        return {"ok": True, "access_token": res.data.get("access_token"),
                "refresh_token": res.data.get("refresh_token"),
                "expires_at": _expires_at(res.data.get("expires_in"))}
    transient = res.status is None or (res.status or 0) >= 500
    return {"ok": False, "transient": transient, "error": res.error or "refresh failed"}


def revoke(token: Optional[str]) -> None:
    if not token:
        return
    try:
        _http.request_json("POST", REVOKE_URL, data={"token": token},
                           headers={"Content-Type": "application/x-www-form-urlencoded"},
                           timeout=10, max_retries=1, guard_redirects=True, parse_json=False)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Search Console API
# ---------------------------------------------------------------------------
def list_sites(access_token: str) -> list[dict]:
    """Verified properties for the property picker (filters out unverified)."""
    res = _http.request_json("GET", f"{GSC_BASE}/sites",
                             headers={"Authorization": f"Bearer {access_token}"},
                             timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return []
    out = []
    for s in res.data.get("siteEntry") or []:
        if s.get("permissionLevel") == "siteUnverifiedUser":
            continue
        out.append({"property": s.get("siteUrl"), "permission": s.get("permissionLevel")})
    return out


def verify_access(access_token: str, prop: str) -> bool:
    """Cheap liveness probe for status._probe_gsc (a 1-day analytics query)."""
    today = datetime.now(timezone.utc).date()
    res = query_search_analytics(access_token, prop,
                                 start_date=(today - timedelta(days=5)).isoformat(),
                                 end_date=(today - timedelta(days=3)).isoformat(),
                                 dimensions=["date"], row_limit=1)
    return res.get("ok", False)


def query_search_analytics(access_token: str, prop: str, *, start_date: str, end_date: str,
                           dimensions: list[str], row_limit: int = 25000, start_row: int = 0,
                           data_state: str = "final", search_type: str = "web") -> dict:
    """POST searchAnalytics/query. Returns {ok, rows:[{keys,clicks,impressions,ctr,position}]}.
    The property is URL-encoded in the path (handles both https://… and sc-domain:… forms)."""
    body = {"startDate": start_date, "endDate": end_date, "dimensions": dimensions,
            "rowLimit": row_limit, "startRow": start_row, "dataState": data_state,
            "type": search_type}
    url = f"{GSC_BASE}/sites/{quote(prop, safe='')}/searchAnalytics/query"
    res = _http.request_json("POST", url,
                             headers={"Authorization": f"Bearer {access_token}",
                                      "Content-Type": "application/json"},
                             json=body, timeout=40, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "status": res.status, "error": res.error, "rows": []}
    return {"ok": True, "rows": res.data.get("rows") or []}
