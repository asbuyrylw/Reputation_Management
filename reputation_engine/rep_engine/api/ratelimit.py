"""Tiny in-process sliding-window rate limiter for login (brute-force slowdown).

Process-local (fine for local-first / a single API process; for multi-process use a
shared store later). Disabled under pytest so the suite's many logins don't trip it;
the limiter function itself is unit-tested directly.
"""

from __future__ import annotations

import sys
import time
from typing import Dict, List

WINDOW = 60.0        # seconds
MAX_ATTEMPTS = 10    # per key per window

_ATTEMPTS: Dict[str, List[float]] = {}


def rate_check(key: str) -> bool:
    """Record an attempt for `key`; return True if under the limit, False if over."""
    now = time.monotonic()
    bucket = [t for t in _ATTEMPTS.get(key, []) if now - t < WINDOW]
    bucket.append(now)
    _ATTEMPTS[key] = bucket
    return len(bucket) <= MAX_ATTEMPTS


def enabled() -> bool:
    return "pytest" not in sys.modules


def reset() -> None:
    _ATTEMPTS.clear()
