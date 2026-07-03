"""
Google Business Profile publish adapter -- local posts (Integrations Phase 5)
=============================================================================
Posts a local "What's new" update to a GBP location. Distinct from review replies (gbp_reviews).
Requires an OAuth connection with gbp_access='approved' (gated at target creation). Host pinned.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from .. import http as _http
    from .base import Connection, PublishPayload, PublishResult, Capability
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    from publishing.base import Connection, PublishPayload, PublishResult, Capability  # type: ignore

GBP_BASE = os.getenv("GBP_API_BASE", "https://mybusinessaccountmanagement.googleapis.com/v4")
GBP_POST_BASE = os.getenv("GBP_POST_BASE", "https://mybusiness.googleapis.com/v4")


class GoogleBusinessPublisher:
    provider = "google_business"

    def capabilities(self, conn: Connection) -> Capability:
        return Capability(social=True, link=True)

    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult:
        token = conn.access_token
        cfg = conn.config or {}
        account = cfg.get("account_id") or ""
        location = cfg.get("location_id") or ""
        if not (token and account and location):
            return PublishResult(status="failed", error="missing GBP account/location/token", retryable=False)
        summary = payload.text or payload.body_markdown or payload.title or ""
        body: dict = {"languageCode": "en-US", "summary": summary[:1500], "topicType": "STANDARD"}
        if payload.link_url:
            body["callToAction"] = {"actionType": "LEARN_MORE", "url": payload.link_url}
        name = f"{account}/{location}".lstrip("/")
        res = _http.request_json(
            "POST", f"{GBP_POST_BASE}/{name}/localPosts",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body, timeout=30, max_retries=2, guard_redirects=True)
        if res.ok and isinstance(res.data, dict):
            d = res.data
            return PublishResult(status="live", external_url=d.get("searchUrl"),
                                 external_id=d.get("name"), http_status=res.status)
        if res.status in (401, 403):
            return PublishResult(status="failed", error=res.error, retryable=False,
                                 http_status=res.status, auth_failed=True)
        retryable = res.status is None or (res.status or 0) >= 500 or res.status == 429
        return PublishResult(status="failed", error=res.error or "GBP post failed",
                             retryable=retryable, http_status=res.status)
