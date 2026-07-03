"""
WordPress publish adapter (Integrations Phase 2)
================================================
Publishes an approved article to the tenant's OWN WordPress site via the REST API, authenticated
with the stored Application Password (HTTP Basic over HTTPS-only). Scheduling uses `date_gmt`
(UTC) + `status='future'` so the wall-clock is correct on non-UTC sites. All I/O is SSRF-guarded.
Stateless: no DB access here -- the runner owns persistence.
"""

from __future__ import annotations

import base64
from typing import Optional
from urllib.parse import urlparse

try:
    from .. import http as _http
    from .. import netguard as _ng
    from .base import Connection, PublishPayload, PublishResult, Capability
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    import netguard as _ng  # type: ignore
    from publishing.base import Connection, PublishPayload, PublishResult, Capability  # type: ignore


class WordPressPublisher:
    provider = "wordpress"

    def capabilities(self, conn: Connection) -> Capability:
        return Capability(article=True, link=True, schedule=True, draft_then_publish=True)

    def _auth_header(self, conn: Connection) -> str:
        user = (conn.config or {}).get("wp_user") or ""
        token = base64.b64encode(f"{user}:{conn.access_token}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _site(self, conn: Connection) -> Optional[str]:
        site = ((conn.config or {}).get("site_url") or "").rstrip("/")
        if not site or urlparse(site).scheme != "https":
            return None
        try:
            _ng.assert_url_allowed(site)
        except Exception:  # noqa: BLE001
            return None
        return site

    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult:
        site = self._site(conn)
        if not site:
            return PublishResult(status="failed", error="site URL missing/non-https/blocked", retryable=False)
        content = payload.body_html or payload.body_markdown or payload.text or ""
        body: dict = {"title": payload.title or "(untitled)", "content": content}
        if payload.scheduled_at:
            # WP expects an ISO datetime *without* trailing 'Z' in date_gmt; strip if present.
            body["status"] = "future"
            body["date_gmt"] = payload.scheduled_at.replace("Z", "")
        else:
            body["status"] = "publish"
        res = _http.request_json(
            "POST", f"{site}/wp-json/wp/v2/posts",
            headers={"Authorization": self._auth_header(conn), "Content-Type": "application/json"},
            json=body, timeout=30, max_retries=2, guard_redirects=True)
        if res.ok and isinstance(res.data, dict):
            d = res.data
            scheduled = (d.get("status") == "future")
            return PublishResult(
                status="scheduled" if scheduled else "live",
                external_url=d.get("link"), external_id=str(d.get("id") or ""),
                http_status=res.status)
        # Failure classification
        if res.status in (401, 403):
            return PublishResult(status="failed", error=res.error, retryable=False,
                                 http_status=res.status, auth_failed=True)
        retryable = res.status is None or (res.status or 0) >= 500 or res.status == 429
        return PublishResult(status="failed", error=res.error, retryable=retryable, http_status=res.status)
