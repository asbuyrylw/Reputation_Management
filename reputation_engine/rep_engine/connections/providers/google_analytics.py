"""
Google Analytics (GA4) OAuth provider + Data API client (Wave 1)
================================================================
Read-only behavioral data (sessions/users/pageviews/conversions/engagement). Shares the Google
OAuth client + token endpoints with the other Google providers but is a SEPARATE module so the
analytics.readonly scope never entangles with GBP/GSC scopes. All I/O SSRF-guarded, host-pinned.

A GA4 "property" is `properties/{numericId}`; the Data API path uses the numeric id.
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
GA_ADMIN_BASE = "https://analyticsadmin.googleapis.com/v1beta"
GA_DATA_BASE = "https://analyticsdata.googleapis.com/v1beta"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def configured() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID") and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"))


def authorize_url(state: str, redirect_uri: str) -> str:
    q = {"client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""), "redirect_uri": redirect_uri,
         "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline",
         "include_granted_scopes": "true", "prompt": "consent", "state": state}
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
    return {"ok": True, "access_token": d.get("access_token"), "refresh_token": d.get("refresh_token"),
            "expires_at": _expires_at(d.get("expires_in")), "scopes": (d.get("scope") or "").split() or SCOPES}


def refresh(creds: dict) -> dict:
    if not configured():
        return {"ok": False, "error": "GOOGLE_OAUTH_CLIENT_ID/SECRET not set"}
    rt = creds.get("refresh_token")
    if not rt:
        return {"ok": False, "error": "no refresh token stored"}
    res = _http.request_json(
        "POST", TOKEN_URL,
        data={"refresh_token": rt, "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
              "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""), "grant_type": "refresh_token"},
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
# GA4 Admin + Data API
# ---------------------------------------------------------------------------
def list_properties(access_token: str) -> list[dict]:
    """GA4 properties for the property picker (via account summaries)."""
    res = _http.request_json("GET", f"{GA_ADMIN_BASE}/accountSummaries",
                             headers={"Authorization": f"Bearer {access_token}"},
                             timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return []
    out = []
    for acc in res.data.get("accountSummaries") or []:
        for p in acc.get("propertySummaries") or []:
            out.append({"property": p.get("property"),  # "properties/123456"
                        "display_name": p.get("displayName"),
                        "account": acc.get("displayName")})
    return out


def _property_id(prop: str) -> str:
    return (prop or "").split("/")[-1]


def run_report(access_token: str, prop: str, *, dimensions: list[str], metrics: list[str],
               start_date: str, end_date: str, limit: int = 10000) -> dict:
    """POST properties/{id}:runReport. Returns {ok, rows:[{dims:[...], metrics:[...]}]}."""
    body = {"dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "dimensions": [{"name": d} for d in dimensions],
            "metrics": [{"name": m} for m in metrics], "limit": limit}
    url = f"{GA_DATA_BASE}/properties/{_property_id(prop)}:runReport"
    res = _http.request_json("POST", url,
                             headers={"Authorization": f"Bearer {access_token}",
                                      "Content-Type": "application/json"},
                             json=body, timeout=40, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "status": res.status, "error": res.error, "rows": []}
    rows = []
    for r in res.data.get("rows") or []:
        rows.append({"dims": [d.get("value") for d in r.get("dimensionValues") or []],
                     "metrics": [m.get("value") for m in r.get("metricValues") or []]})
    return {"ok": True, "rows": rows}
