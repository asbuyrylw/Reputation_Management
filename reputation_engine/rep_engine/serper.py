"""
Cached Serper client (Phase E efficiency)
=========================================
A thin TTL cache in front of Serper. The audit battery, competitor benchmark, local-rank tracker,
GBP ingest, and the social audit all issue overlapping category-local queries; without a cache each
identical query is paid for again. cached_post() collapses duplicates within the TTL window into a
single billed call, with zero behavior change for callers.

Keyless/dormant-safe: with no SERPER_API_KEY it returns None (callers already handle that). Cache
failures degrade to a live call -- the cache can never break a request.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

try:
    from . import http as _http
    from . import cost as _cost
    from .db import db
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    import cost as _cost  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("serper")

SERPER_BASE = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")
# Default TTL: a day is plenty for SERP/place data within one audit cycle while still refreshing
# day-over-day. Override with SERPER_CACHE_TTL_HOURS=0 to disable the cache.
_TTL_HOURS = float(os.getenv("SERPER_CACHE_TTL_HOURS", "24"))


def _key(endpoint: str, body: dict) -> str:
    norm = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(f"{endpoint}\n{norm}".encode("utf-8")).hexdigest()


def _get_cached(key: str) -> Optional[dict]:
    if _TTL_HOURS <= 0:
        return None
    try:
        with db() as conn:
            r = conn.execute(
                "SELECT response FROM serper_cache WHERE cache_key=%s "
                "AND created_at > now() - (%s * interval '1 hour')", (key, _TTL_HOURS),
            ).fetchone()
        return r["response"] if r else None
    except Exception as e:  # noqa: BLE001 -- a cache miss/error must never block the call
        log.debug("serper cache read skipped: %s", e)
        return None


def _store(key: str, endpoint: str, data: dict) -> None:
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO serper_cache (cache_key, endpoint, response, created_at) "
                "VALUES (%s,%s,%s, now()) ON CONFLICT (cache_key) DO UPDATE SET "
                "response=EXCLUDED.response, created_at=now()",
                (key, endpoint, json.dumps(data, default=str)),
            )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        log.debug("serper cache write skipped: %s", e)


def cached_post(endpoint: str, body: dict, *, timeout: int = 20, max_retries: int = 2,
                business_id: Optional[int] = None, run_id: Optional[int] = None) -> Optional[dict]:
    """POST to a Serper endpoint with a TTL cache. Returns the parsed dict, or None when the key is
    missing or the call fails. A cache HIT costs nothing; only a real (miss) call is billed, so we
    record cost exactly once per real API call, attributed to business_id when the caller supplies it."""
    key_env = os.getenv("SERPER_API_KEY", "")
    if not key_env:
        return None
    ck = _key(endpoint, body)
    hit = _get_cached(ck)
    if hit is not None:
        return hit
    if business_id is not None:
        projected, _label = _cost.ext_estimate("search", 1)
        if _cost.would_exceed(business_id, projected):
            log.warning("serper %s skipped for business %s: projected call would exceed budget",
                        endpoint, business_id)
            return None
    res = _http.request_json("POST", f"{SERPER_BASE}/{endpoint}",
                             headers={"X-API-KEY": key_env, "Content-Type": "application/json"},
                             json=body, timeout=timeout, max_retries=max_retries)
    if res.failed or not isinstance(res.data, dict):
        return None
    _store(ck, endpoint, res.data)
    try:  # cost tracking is best-effort; must never break a search
        _cost.record_cost(business_id, run_id, "search", "serper", endpoint,
                          units=1, detail={"endpoint": endpoint})
    except Exception:  # noqa: BLE001
        pass
    return res.data
