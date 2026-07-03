"""
Ayrshare publish adapter -- social fan-out (Integrations Phase 5)
================================================================
ONE adapter for all social networks via Ayrshare's hosted account-linking. Network-grain: the
runner created one target per network, so each publish() posts to exactly ONE network and returns
one result -- no per-call fan-out, no partial collapse. Auth = business API key (env) + per-tenant
profile key (encrypted per connection). Host pinned to api.ayrshare.com.
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

AYRSHARE_POST_URL = "https://api.ayrshare.com/api/post"

# registry network -> Ayrshare platform name
_NETWORK_MAP = {
    "facebook": "facebook", "instagram": "instagram", "linkedin": "linkedin",
    "twitter": "twitter", "x": "twitter", "pinterest": "pinterest",
}


class AyrsharePublisher:
    provider = "ayrshare"

    def capabilities(self, conn: Connection) -> Capability:
        return Capability(social=True, link=True, schedule=True)

    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult:
        api_key = os.getenv("AYRSHARE_API_KEY", "")
        if not api_key:
            return PublishResult(status="failed", error="AYRSHARE_API_KEY not set", retryable=False)
        profile_key = (conn.config or {}).get("profile_key")
        platform = _NETWORK_MAP.get((payload.network or "").lower())
        if not platform:
            return PublishResult(status="failed", error=f"unmapped network {payload.network}", retryable=False)
        text = payload.text or payload.body_markdown or payload.title or ""
        if payload.link_url:
            text = f"{text}\n{payload.link_url}".strip()
        body: dict = {"post": text, "platforms": [platform]}
        if payload.scheduled_at:
            body["scheduleDate"] = payload.scheduled_at
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if profile_key:
            headers["Profile-Key"] = profile_key
        res = _http.request_json("POST", AYRSHARE_POST_URL, headers=headers, json=body,
                                 timeout=30, max_retries=2, guard_redirects=True)
        if res.ok and isinstance(res.data, dict) and res.data.get("status") in (None, "success", "scheduled"):
            d = res.data
            posts = d.get("postIds") or d.get("posts") or []
            ext_url = ext_id = None
            if posts and isinstance(posts, list) and isinstance(posts[0], dict):
                ext_url = posts[0].get("postUrl") or posts[0].get("url")
                ext_id = posts[0].get("id") or posts[0].get("postId")
            scheduled = bool(payload.scheduled_at)
            return PublishResult(status="scheduled" if scheduled else "live",
                                 external_url=ext_url, external_id=str(ext_id) if ext_id else None,
                                 http_status=res.status)
        if res.status in (401, 403):
            return PublishResult(status="failed", error=res.error, retryable=False,
                                 http_status=res.status, auth_failed=True)
        retryable = res.status is None or (res.status or 0) >= 500 or res.status == 429
        return PublishResult(status="failed", error=res.error or "ayrshare post failed",
                             retryable=retryable, http_status=res.status)
