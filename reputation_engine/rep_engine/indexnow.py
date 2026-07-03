"""
IndexNow -- instant re-crawl on publish (adopted from SnowSEO)
=============================================================
When owned content is published/updated, ping IndexNow so Bing/Yandex (and other participating
engines) re-crawl it within minutes instead of waiting days. Cheap, white-hat, and it shortens the
loop from "we published a fix" to "the engines see it."

Setup (one-time per site): generate a key, host it at https://<site>/<key>.txt containing the key,
and set INDEXNOW_KEY. Dormant-safe -- with no key every call is a {skipped} no-op. Host-pinned to
api.indexnow.org via the SSRF-guarded http client.

Docs: https://www.indexnow.org/documentation
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

log = logging.getLogger("indexnow")

_ENDPOINT = "https://api.indexnow.org/indexnow"


def _key() -> str:
    return (os.getenv("INDEXNOW_KEY") or "").strip()


def configured() -> bool:
    return bool(_key())


def _key_location(host: str) -> str:
    # default convention: the key file lives at the site root. Override via INDEXNOW_KEY_LOCATION.
    loc = (os.getenv("INDEXNOW_KEY_LOCATION") or "").strip()
    return loc or f"https://{host}/{_key()}.txt"


def submit(urls: list[str]) -> dict:
    """Submit one or more URLs (same host) to IndexNow. Returns {submitted, host} or {skipped}."""
    if not configured():
        return {"skipped": True, "reason": "INDEXNOW_KEY not set"}
    clean = [u for u in (urls or []) if u and u.lower().startswith("http")]
    if not clean:
        return {"skipped": True, "reason": "no http urls"}
    host = urlparse(clean[0]).netloc
    # IndexNow requires all URLs in one request share the host the key is hosted on.
    same_host = [u for u in clean if urlparse(u).netloc == host][:10000]
    body = {"host": host, "key": _key(), "keyLocation": _key_location(host), "urlList": same_host}
    res = _http.request_json("POST", _ENDPOINT, headers={"Content-Type": "application/json"},
                             json=body, timeout=20, max_retries=2, guard_redirects=True)
    if res.failed:
        log.warning("IndexNow submit failed (%s): %s", host, res.error)
        return {"skipped": True, "reason": res.error, "host": host}
    return {"submitted": len(same_host), "host": host, "http_status": res.status}


def submit_url(url: str) -> dict:
    """Convenience: submit a single published/updated URL. Never raises."""
    try:
        return submit([url])
    except Exception as e:  # noqa: BLE001 -- indexing must never break the publish path
        log.debug("IndexNow submit_url skipped: %s", e)
        return {"skipped": True, "reason": str(e)}
