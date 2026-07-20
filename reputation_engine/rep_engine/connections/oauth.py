"""
OAuth handshake -- single-use, domain-separated state + provider dispatch (Phase 1)
==================================================================================
`build_state()` mints a high-entropy state, HMAC-signs it (domain-separated), and persists a
10-minute `oauth_states` row. `verify_state()` does a single-use `DELETE ... RETURNING` in the
same transaction as the code exchange and verifies the HMAC with `compare_digest` -- so a state
cannot be replayed or forged. The post-callback redirect is a FIXED internal path keyed by
platform; a client-supplied redirect_uri is never reflected (no open redirect).
"""

from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

try:
    from ..db import db
    from . import providers
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import connections.providers as providers  # type: ignore

from psycopg.types.json import Json  # noqa: F401  (kept for symmetry with vault writes)

# kind -> provider module. Only OAuth providers belong here (WordPress/Ayrshare are non-OAuth).
_OAUTH_PROVIDERS = {
    "google_business_profile": "google",
    "google_search_console": "google_search_console",
    "google_analytics": "google_analytics",
    "youtube": "youtube",
}
STATE_TTL_MIN = 10


def _state_secret() -> bytes:
    sec = os.getenv("OAUTH_STATE_SECRET") or os.getenv("JWT_SECRET") or ""
    return sec.encode("utf-8")


def _sign(raw: str) -> str:
    return hmac.new(_state_secret(), b"oauth-state|" + raw.encode("utf-8"), sha256).hexdigest()


def _provider(platform: str):
    name = _OAUTH_PROVIDERS.get(platform)
    if not name:
        raise ValueError(f"unsupported OAuth platform: {platform}")
    import importlib
    return importlib.import_module(f"{providers.__name__}.{name}")


def redirect_uri(platform: str) -> str:
    """Fixed callback URL the provider redirects back to (routed through the console /api proxy)."""
    origin = (os.getenv("PUBLIC_APP_ORIGIN") or "http://localhost:3000").rstrip("/")
    return f"{origin}/api/connections/{platform}/callback"


def callback_landing(platform: str, ok: bool, reason: str = "") -> str:
    """Fixed internal console path to bounce the browser to after the callback (never client-supplied)."""
    origin = (os.getenv("PUBLIC_APP_ORIGIN") or "http://localhost:3000").rstrip("/")
    status = "connected" if ok else "error"
    suffix = f"&reason={reason}" if (reason and not ok) else ""
    return f"{origin}/integrations?{status}={platform}{suffix}"


def provider_configured(platform: str) -> bool:
    try:
        return bool(_provider(platform).configured())
    except Exception:  # noqa: BLE001
        return False


def build_state(business_id: int, platform: str, created_by: Optional[int] = None) -> dict:
    """Mint state, persist a single-use row, and return {authorize_url, state}."""
    prov = _provider(platform)  # raises ValueError on unsupported platform
    if not prov.configured():
        raise ValueError(f"{platform} OAuth is not configured on this server")
    raw = secrets.token_urlsafe(32)
    state = f"{raw}.{_sign(raw)}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MIN)
    with db() as conn:
        conn.execute(
            "INSERT INTO oauth_states (state, business_id, platform, redirect_uri, created_by, expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (raw, business_id, platform, redirect_uri(platform), created_by, expires))
        conn.commit()
    return {"authorize_url": prov.authorize_url(state, redirect_uri(platform)), "state": state}


def verify_state(state: str) -> dict:
    """Single-use consume + HMAC verify. Returns {business_id, platform, redirect_uri}. Raises
    ValueError (-> 403 at the router) if absent, expired, or tampered."""
    if not state or "." not in state:
        raise ValueError("missing or malformed state")
    raw, _, sig = state.partition(".")
    if not hmac.compare_digest(sig, _sign(raw)):
        raise ValueError("state signature mismatch")
    with db() as conn:
        row = conn.execute(
            "DELETE FROM oauth_states WHERE state=%s "
            "RETURNING business_id, platform, redirect_uri, created_by, expires_at",
            (raw,)).fetchone()
        conn.commit()
    if not row:
        raise ValueError("state not found (already used or unknown)")
    exp = row["expires_at"]
    if exp and exp < datetime.now(timezone.utc):
        raise ValueError("state expired")
    return {"business_id": row["business_id"], "platform": row["platform"],
            "redirect_uri": row["redirect_uri"], "created_by": row["created_by"]}


def exchange(platform: str, code: str, redirect: str) -> dict:
    return _provider(platform).exchange_code(code, redirect)


def refresh_token(kind: str, creds: dict) -> dict:
    """Dispatch a refresh to the matching provider. Unknown/non-OAuth kinds are a no-op success."""
    name = _OAUTH_PROVIDERS.get(kind)
    if not name:
        return {"ok": True, "noop": True}
    return _provider(kind).refresh(creds)


def prune_expired() -> int:
    with db() as conn:
        n = conn.execute("DELETE FROM oauth_states WHERE expires_at < now()").rowcount
        conn.commit()
    return int(n or 0)
