"""
Reputation Crowding-Out Engine -- integration env flags + secret redaction (Phase 0)
====================================================================================
Tiny, dependency-free helpers shared across the connections/publishing/approval layers:

  * `autopost_global_enabled()` -- the platform-wide kill switch. Default OFF: even a tenant
    that has opted into auto-post cannot publish/reply automatically until an operator sets
    AUTOPOST_GLOBAL_ENABLED=true. The publish/reply runners check this before any auto-driven
    post (manual, human-approved publishes are unaffected).

  * `redact(value)` -- scrub secret-shaped substrings out of any string/dict before it lands in
    a durable column (`*.last_error`, `publish_attempts.request/response_summary`,
    `review_replies.external_ack`). Plaintext tokens must never reach the DB or a log line.
"""

from __future__ import annotations

import os
import re
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def autopost_global_enabled() -> bool:
    """Platform-wide auto-post master switch (default off)."""
    return _truthy_env("AUTOPOST_GLOBAL_ENABLED", "false")


def pressranger_enabled() -> bool:
    """PressRanger press-release task-linking (default OFF until the Claude MCP is set up).
    While off, the 'Corroborate' task instruction stays generic instead of naming PressRanger."""
    return _truthy_env("PRESSRANGER_ENABLED", "false")


# Secret-bearing patterns -> REDACTED. Broader than http._redact (which only scrubs URL query
# params): this also catches bare bearer/basic tokens, app-password fields, and Fernet ciphertext
# shapes that might appear in a provider error body we persist.
_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer|basic)\s+\S+"),
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)((?:access|refresh|id)[_-]?token|app[_-]?password|client[_-]?secret|"
               r"api[_-]?key|profile[_-]?key)\s*[\"']?\s*[:=]\s*[\"']?[^\s\"',}&]+"),
    re.compile(r"\bgAAAAA[A-Za-z0-9_\-]{20,}"),  # Fernet ciphertext prefix
    re.compile(r"(?i)\b(x-(?:api|goog-api)-key)\s*[:=]\s*\S+"),
]

_REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Recursively redact secret-shaped substrings from a str / list / dict. Non-str leaves
    pass through unchanged. Safe to call on anything destined for a durable column or a log."""
    if value is None:
        return None
    if isinstance(value, str):
        out = value
        for pat in _SECRET_PATTERNS:
            out = pat.sub(lambda m: (m.group(1) + " " + _REDACTED) if m.lastindex else _REDACTED, out)
        return out
    if isinstance(value, dict):
        # Drop obviously-secret keys entirely; redact the rest by value.
        cleaned = {}
        for k, v in value.items():
            kl = str(k).lower()
            if any(s in kl for s in ("token", "password", "secret", "api_key", "apikey",
                                     "authorization", "profile_key", "profilekey")):
                cleaned[k] = _REDACTED
            else:
                cleaned[k] = redact(v)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
