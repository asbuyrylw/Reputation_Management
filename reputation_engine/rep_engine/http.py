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
                 parse_json: bool = True) -> HttpResult:
    """Make an HTTP request with retries. Returns HttpResult; never raises for
    network/HTTP errors (raises only on programmer error)."""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(
                method, url, headers=headers, json=json, params=params, timeout=timeout
            )
            status = resp.status_code
            if status in RETRYABLE_STATUS and attempt < max_retries:
                delay = _sleep_for(attempt, resp.headers.get("Retry-After"), base_delay)
                log.warning("HTTP %s on %s (attempt %d/%d) -> retrying in %.1fs",
                            status, _short(url), attempt + 1, max_retries, delay)
                time.sleep(delay)
                continue
            if status >= 400:
                return HttpResult(ok=False, status=status, text=resp.text[:500],
                                  error=f"HTTP {status}: {resp.text[:200]}",
                                  attempts=attempt + 1)
            data = None
            if parse_json:
                try:
                    data = resp.json()
                except ValueError:
                    return HttpResult(ok=False, status=status, text=resp.text[:500],
                                      error="response was not valid JSON",
                                      attempts=attempt + 1)
            return HttpResult(ok=True, status=status, data=data,
                              text=resp.text, attempts=attempt + 1)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = str(e)
            if attempt < max_retries:
                delay = _sleep_for(attempt, None, base_delay)
                log.warning("Network error on %s (attempt %d/%d): %s -> retry in %.1fs",
                            _short(url), attempt + 1, max_retries, e, delay)
                time.sleep(delay)
                continue
        except requests.RequestException as e:
            last_err = str(e)
            break
    return HttpResult(ok=False, error=f"exhausted retries: {last_err}",
                      attempts=max_retries + 1)


def _short(url: str) -> str:
    return url.split("?")[0]
