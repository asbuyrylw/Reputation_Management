"""
Reputation Crowding-Out Engine -- Resilient HTTP helper
======================================================
One place for network resilience so every provider adapter behaves consistently:
  - Exponential backoff with jitter on 429 / 5xx / timeouts / connection errors.
  - Honors Retry-After when present.
  - Returns a structured Result that DISTINGUISHES "the call failed" from "the
    model returned nothing" -- so a transient 429 is never silently recorded as a
    real empty answer (the bug that would quietly corrupt audits).

Usage:
    from .http import request_json, HttpResult
    res = request_json("POST", url, headers=..., json=...)
    if res.ok:
        data = res.data
    elif res.failed:
        # transient/exhausted failure -- caller should mark the datapoint as
        # FAILED, not as an empty answer
        log.warning(res.error)
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

log = logging.getLogger("http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 4
DEFAULT_BASE_DELAY = 1.5     # seconds; doubled each retry
DEFAULT_TIMEOUT = 60


@dataclass
class HttpResult:
    ok: bool
    status: Optional[int] = None
    data: Any = None
    text: str = ""
    error: Optional[str] = None
    attempts: int = 0

    @property
    def failed(self) -> bool:
        """True when the request could not be completed (vs. a successful call
        that legitimately returned empty/blank content)."""
        return not self.ok


def _sleep_for(attempt: int, retry_after: Optional[str], base: float) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except (TypeError, ValueError):
            pass
    # exponential backoff with full jitter
    return min(base * (2 ** attempt) + random.uniform(0, base), 60.0)


def request_json(method: str, url: str, *, headers: dict | None = None,
                 json: dict | None = None, params: dict | None = None,
                 timeout: int = DEFAULT_TIMEOUT, max_retries: int = DEFAULT_MAX_RETRIES,
                 base_delay: float = DEFAULT_BASE_DELAY,
                 parse_json: bool = True, guard_redirects: bool = False,
                 deadline: float | None = None) -> HttpResult:
    """Make an HTTP request with retries. Returns HttpResult; never raises for
    network/HTTP errors (raises only on programmer error).

    When guard_redirects=True, redirects are followed manually (max 5 hops) and
    every hop URL is re-validated by netguard.assert_url_allowed, preventing a
    30x response from redirecting an outbound crawl fetch to an internal address.

    deadline is an optional TOTAL wall-clock budget (seconds) across all retries:
    when set, the call stops retrying once the next backoff would overrun it and
    each attempt's socket timeout is bounded by the remaining budget. Default None
    preserves the prior behavior exactly (per-attempt `timeout` only, worst-case
    total ~= (max_retries+1)*timeout + sum(backoffs))."""
    last_err = None
    last_status = None
    follow = not guard_redirects
    attempts_made = 0
    start = time.monotonic()
    for attempt in range(max_retries + 1):
        # With a deadline set, stop once it's spent and bound each attempt's socket
        # timeout by the remaining budget. This whole block is inert when deadline
        # is None, so existing callers' timing is byte-for-byte unchanged.
        eff_timeout: float = timeout
        if deadline is not None:
            remaining = deadline - (time.monotonic() - start)
            if remaining <= 0:
                break
            eff_timeout = max(1.0, min(float(timeout), remaining))
        attempts_made = attempt + 1
        try:
            resp = requests.request(
                method, url, headers=headers, json=json, params=params,
                timeout=eff_timeout, allow_redirects=follow,
            )
            if guard_redirects:
                hops = 0
                while resp.is_redirect and resp.next is not None and hops < 5:
                    nxt = resp.next.url
                    try:
                        from . import netguard as _ng
                    except ImportError:  # pragma: no cover
                        import netguard as _ng  # type: ignore
                    try:
                        _ng.assert_url_allowed(nxt)
                    except _ng.UnsafeURLError as e:
                        return HttpResult(ok=False, status=resp.status_code,
                                          error=f"redirect blocked by SSRF guard: {e}",
                                          attempts=attempts_made)
                    resp = requests.request(
                        "GET", nxt, headers=headers, params=params,
                        timeout=eff_timeout, allow_redirects=False,
                    )
                    hops += 1
            status = resp.status_code
            last_status = status
            if status in RETRYABLE_STATUS and attempt < max_retries:
                delay = _sleep_for(attempt, resp.headers.get("Retry-After"), base_delay)
                # only retry if the backoff fits the remaining wall-clock budget
                if deadline is None or (time.monotonic() - start) + delay <= deadline:
                    log.warning("HTTP %s on %s (attempt %d/%d) -> retrying in %.1fs",
                                status, _short(url), attempt + 1, max_retries, delay)
                    time.sleep(delay)
                    continue
                # else: out of budget -> fall through and return the status below
            if status >= 400:
                return HttpResult(ok=False, status=status, text=resp.text[:500],
                                  error=f"HTTP {status}: {resp.text[:200]}",
                                  attempts=attempts_made)
            data = None
            if parse_json:
                try:
                    data = resp.json()
                except ValueError:
                    return HttpResult(ok=False, status=status, text=resp.text[:500],
                                      error="response was not valid JSON",
                                      attempts=attempts_made)
            return HttpResult(ok=True, status=status, data=data,
                              text=resp.text, attempts=attempts_made)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = _redact(str(e))
            if attempt >= max_retries:
                break
            delay = _sleep_for(attempt, None, base_delay)
            if deadline is not None and (time.monotonic() - start) + delay > deadline:
                break  # out of wall-clock budget
            log.warning("Network error on %s (attempt %d/%d): %s -> retry in %.1fs",
                        _short(url), attempt + 1, max_retries, last_err, delay)
            time.sleep(delay)
        except requests.RequestException as e:
            last_err = _redact(str(e))
            break
    # last_status carries the most recent observed HTTP status so a deadline that
    # expires DURING a retry backoff still reports the 5xx it saw, rather than a
    # bare status=None. It stays None on pure network-error / no-attempt paths.
    msg = (f"exhausted retries: {last_err}" if last_err
           else f"exhausted retries after {attempts_made} attempt(s)")
    if last_err is None and last_status is not None:
        msg += f" (last status {last_status})"
    return HttpResult(ok=False, status=last_status, error=msg, attempts=attempts_made)


def _short(url: str) -> str:
    return url.split("?")[0]


# Scrub credentials that can ride along in an exception/URL string before they are
# logged or returned in an error (e.g. ?key=..., Bearer ..., x-api-key=...).
_SECRET_RE = re.compile(
    r"(key=|api[_-]?key=|access_token=|token=)[^&\s'\")]+"
    r"|(Bearer\s+)\S+"
    r"|(x-(?:api|goog-api)-key['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+",
    re.I,
)


def _redact(s: str) -> str:
    """Replace secret-bearing query params / auth tokens in a string with REDACTED."""
    return _SECRET_RE.sub(
        lambda m: (m.group(1) or m.group(2) or m.group(3) or "") + "REDACTED", s or ""
    )
