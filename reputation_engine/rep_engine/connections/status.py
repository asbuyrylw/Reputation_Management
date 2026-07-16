"""
Connection liveness probe (Integrations Phase 1)
================================================
`test_connection()` makes one cheap, read-only provider call to confirm a stored credential
still works, and reconciles `platform_connections.status` accordingly (active | expired/revoked
| error). Used by the `POST /connections/{id}/test` endpoint and the refresh sweep's liveness check.
"""

from __future__ import annotations

import base64
from typing import Optional

try:
    from . import vault
    from .. import http as _http
except ImportError:  # pragma: no cover
    import connections.vault as vault  # type: ignore
    import http as _http  # type: ignore

GBP_ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"


def test_connection(conn_id: int, business_id: int) -> dict:
    """Probe the live provider. Returns {ok, status, detail}. Updates the connection status."""
    creds = vault.credentials(conn_id, business_id)
    if not creds:
        return {"ok": False, "status": "not_found"}
    kind = creds["kind"]
    if kind == "wordpress_org":
        return _probe_wordpress(conn_id, business_id, creds)
    if kind == "google_business_profile":
        return _probe_google(conn_id, business_id, creds)
    if kind == "google_search_console":
        return _probe_gsc(conn_id, business_id, creds)
    if kind == "google_analytics":
        return _probe_ga(conn_id, business_id, creds)
    if kind == "youtube":
        return _probe_youtube(conn_id, business_id, creds)
    if kind == "zernia":
        return _probe_zernia(conn_id, business_id, creds)
    # Non-probeable kinds (e.g. ayrshare profile-key): trust stored state, just touch it.
    vault.touch_used(conn_id)
    return {"ok": True, "status": creds.get("status") or "active", "detail": "no live probe for this provider"}


def _probe_youtube(conn_id: int, business_id: int, creds: dict) -> dict:
    try:
        from .providers import youtube as _yt
    except ImportError:  # pragma: no cover
        from connections.providers import youtube as _yt  # type: ignore
    res = _yt.my_channel(creds.get("access_token") or "")
    if res.get("ok"):
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active", "detail": f"channel: {res.get('title')}"}
    vault.mark_status(conn_id, "error", last_error=(res.get("error") or "probe failed")[:200],
                      business_id=business_id)
    return {"ok": False, "status": "error", "detail": res.get("error")}


def _probe_wordpress(conn_id: int, business_id: int, creds: dict) -> dict:
    meta = creds.get("meta") or {}
    site = (meta.get("site_url") or "").rstrip("/")
    user = meta.get("wp_user") or ""
    secret = creds.get("access_token") or ""
    if not (site and user and secret):
        vault.mark_status(conn_id, "error", last_error="missing site/user/credential", business_id=business_id)
        return {"ok": False, "status": "error"}
    tok = base64.b64encode(f"{user}:{secret}".encode("utf-8")).decode("ascii")
    res = _http.request_json("GET", f"{site}/wp-json/wp/v2/users/me",
                             headers={"Authorization": f"Basic {tok}"},
                             timeout=15, max_retries=1, guard_redirects=True)
    if res.ok:
        vault.mark_status(conn_id, "active", business_id=business_id)
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active"}
    new_status = "revoked" if (res.status in (401, 403)) else "error"
    vault.mark_status(conn_id, new_status, last_error=res.error, business_id=business_id)
    return {"ok": False, "status": new_status, "detail": res.error}


def _probe_gsc(conn_id: int, business_id: int, creds: dict) -> dict:
    token = creds.get("access_token")
    if not token:
        vault.mark_status(conn_id, "error", last_error="no access token", business_id=business_id)
        return {"ok": False, "status": "error"}
    try:
        from .providers import google_search_console as _gsc
    except ImportError:  # pragma: no cover
        from connections.providers import google_search_console as _gsc  # type: ignore
    # listing sites is a cheap authenticated read that confirms the token works
    res = _http.request_json("GET", f"{_gsc.GSC_BASE}/sites",
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=15, max_retries=1, guard_redirects=True)
    if res.ok:
        vault.mark_status(conn_id, "active", business_id=business_id)
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active"}
    if res.status in (401, 403):
        vault.revoke_on_runtime_401(conn_id, business_id, res.error)
        return {"ok": False, "status": "revoked", "detail": res.error}
    vault.mark_status(conn_id, "error", last_error=res.error, business_id=business_id)
    return {"ok": False, "status": "error", "detail": res.error}


def _probe_ga(conn_id: int, business_id: int, creds: dict) -> dict:
    token = creds.get("access_token")
    if not token:
        vault.mark_status(conn_id, "error", last_error="no access token", business_id=business_id)
        return {"ok": False, "status": "error"}
    try:
        from .providers import google_analytics as _ga
    except ImportError:  # pragma: no cover
        from connections.providers import google_analytics as _ga  # type: ignore
    res = _http.request_json("GET", f"{_ga.GA_ADMIN_BASE}/accountSummaries",
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=15, max_retries=1, guard_redirects=True)
    if res.ok:
        vault.mark_status(conn_id, "active", business_id=business_id)
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active"}
    if res.status in (401, 403):
        vault.revoke_on_runtime_401(conn_id, business_id, res.error)
        return {"ok": False, "status": "revoked", "detail": res.error}
    vault.mark_status(conn_id, "error", last_error=res.error, business_id=business_id)
    return {"ok": False, "status": "error", "detail": res.error}


def _probe_zernia(conn_id: int, business_id: int, creds: dict) -> dict:
    try:
        from .providers import zernia as _z
    except ImportError:  # pragma: no cover
        from connections.providers import zernia as _z  # type: ignore
    if not _z.configured():
        vault.mark_status(conn_id, "error", last_error="ZERNIA_API_KEY not set", business_id=business_id)
        return {"ok": False, "status": "error", "detail": "Zernio key not configured"}
    if _z.verify():
        vault.mark_status(conn_id, "active", business_id=business_id)
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active"}
    vault.mark_status(conn_id, "error", last_error="Zernio API key invalid or unreachable", business_id=business_id)
    return {"ok": False, "status": "error"}


def _probe_google(conn_id: int, business_id: int, creds: dict) -> dict:
    token = creds.get("access_token")
    if not token:
        vault.mark_status(conn_id, "error", last_error="no access token", business_id=business_id)
        return {"ok": False, "status": "error"}
    res = _http.request_json("GET", GBP_ACCOUNTS_URL,
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=15, max_retries=1, guard_redirects=True)
    if res.ok:
        vault.mark_status(conn_id, "active", business_id=business_id)
        vault.touch_used(conn_id)
        return {"ok": True, "status": "active"}
    if res.status in (401, 403):
        vault.revoke_on_runtime_401(conn_id, business_id, res.error)
        return {"ok": False, "status": "revoked", "detail": res.error}
    vault.mark_status(conn_id, "error", last_error=res.error, business_id=business_id)
    return {"ok": False, "status": "error", "detail": res.error}
