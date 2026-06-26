"""
Zernio publish adapter -- social fan-out (replaces Ayrshare)
===========================================================
Posts one network per call via Zernio's POST /posts. Auth is the account-level key (env), and the
target's network maps to the accountId stored on the connection (conn.config['accounts']) from the
profile's connected accounts. Network-grain: the runner created one target per network, so each
publish() posts to exactly one network. SSRF-guarded, host-pinned to zernio.com.
"""

from __future__ import annotations

try:
    from .. import http as _http
    from ..connections.providers import zernia as _zp
    from .base import Connection, PublishPayload, PublishResult, Capability
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    from connections.providers import zernia as _zp  # type: ignore
    from publishing.base import Connection, PublishPayload, PublishResult, Capability  # type: ignore

# registry network -> Zernio platform slug
_NETWORK_MAP = {
    "facebook": "facebook", "instagram": "instagram", "linkedin": "linkedin",
    "twitter": "twitter", "x": "twitter", "pinterest": "pinterest",
    "tiktok": "tiktok", "youtube": "youtube", "threads": "threads", "bluesky": "bluesky",
}


class ZerniaPublisher:
    provider = "zernia"

    def capabilities(self, conn: Connection) -> Capability:
        return Capability(social=True, link=True, schedule=True)

    def publish(self, conn: Connection, payload: PublishPayload) -> PublishResult:
        if not _zp.configured():
            return PublishResult(status="failed", error="ZERNIA_API_KEY not set", retryable=False)
        platform = _NETWORK_MAP.get((payload.network or "").lower())
        if not platform:
            return PublishResult(status="failed", error=f"unmapped network {payload.network}", retryable=False)
        accounts = (conn.config or {}).get("accounts") or {}
        account_id = accounts.get(platform)
        if not account_id:
            return PublishResult(status="failed",
                                 error=f"no connected {platform} account on this Zernio profile", retryable=False)
        text = payload.text or payload.body_markdown or payload.title or ""
        if payload.link_url:
            text = f"{text}\n{payload.link_url}".strip()
        body: dict = {"content": text, "platforms": [{"platform": platform, "accountId": account_id}]}
        if payload.scheduled_at:
            body["scheduledFor"] = payload.scheduled_at.replace("Z", "")
            body["timezone"] = "UTC"
        else:
            body["publishNow"] = True
        res = _http.request_json("POST", f"{_zp.base()}/posts",
                                 headers={"Authorization": f"Bearer {_zp._key()}", "Content-Type": "application/json"},
                                 json=body, timeout=30, max_retries=2, guard_redirects=True)
        if res.ok and isinstance(res.data, dict):
            post = res.data.get("post") or res.data
            ext_id = post.get("_id") or post.get("id")
            ext_url = post.get("url") or post.get("postUrl")
            scheduled = bool(payload.scheduled_at)
            return PublishResult(status="scheduled" if scheduled else "live",
                                 external_url=ext_url, external_id=str(ext_id) if ext_id else None,
                                 http_status=res.status)
        if res.status in (401, 403):
            return PublishResult(status="failed", error=res.error, retryable=False,
                                 http_status=res.status, auth_failed=True)
        retryable = res.status is None or (res.status or 0) >= 500 or res.status == 429
        return PublishResult(status="failed", error=res.error or "zernio post failed",
                             retryable=retryable, http_status=res.status)
