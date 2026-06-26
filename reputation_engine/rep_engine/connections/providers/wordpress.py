"""
WordPress provider -- Application-Password verification (Integrations Phase 1)
=============================================================================
WordPress.org connects via an HTTP Basic Application Password (no OAuth). The secret is
verified at connect time against `GET {site_url}/wp-json/wp/v2/users/me` over HTTPS-ONLY,
through netguard (rejects non-https + private IPs + DNS-rebind). The publish adapter (Phase 2)
reuses the same Basic credential.
"""

from __future__ import annotations

import base64
from typing import Optional
from urllib.parse import urlparse

try:
    from ... import http as _http
    from ... import netguard as _ng
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    import netguard as _ng  # type: ignore


def _basic_header(user: str, app_password: str) -> str:
    # WordPress application passwords are shown with spaces; they are accepted with or without.
    token = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def normalize_site_url(site_url: str) -> str:
    return (site_url or "").strip().rstrip("/")


def verify_app_password(site_url: str, wp_user: str, app_password: str) -> dict:
    """Verify the app-password against the site. Returns {ok, meta:{site_url,wp_user,...}} or
    {ok:False, error}. HTTPS-only + SSRF-guarded (no posting to an internal address)."""
    site = normalize_site_url(site_url)
    parsed = urlparse(site)
    if parsed.scheme != "https":
        return {"ok": False, "error": "site URL must be https:// (an application password over http is insecure)"}
    try:
        _ng.assert_url_allowed(site)
    except Exception as e:  # noqa: BLE001 -- UnsafeURLError or parse error
        return {"ok": False, "error": f"site URL not allowed: {e}"}
    url = f"{site}/wp-json/wp/v2/users/me"
    res = _http.request_json(
        "GET", url,
        headers={"Authorization": _basic_header(wp_user, app_password)},
        timeout=20, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        return {"ok": False, "error": res.error or "could not reach the WordPress REST API"}
    me = res.data
    caps = me.get("capabilities") or {}
    can_publish = bool(caps.get("publish_posts", True))  # default-true: some setups hide caps
    meta = {"site_url": site, "wp_user": wp_user, "wp_user_id": me.get("id"),
            "wp_display_name": me.get("name"), "can_publish": can_publish, "variant": "org"}
    return {"ok": True, "meta": meta, "account_ref": site}


def site_capabilities(meta: dict) -> dict:
    """Cheap capability read for the UI (no network)."""
    return {"article": True, "link": True, "schedule": True,
            "publish": bool((meta or {}).get("can_publish", True))}
