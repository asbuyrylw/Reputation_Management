"""
Reputation Crowding-Out Engine -- Chrome "Reply Assist" extension tokens
=========================================================================
The extension reads pending drafted replies from a browser content script running on
Yelp/Reddit/Facebook -- outside the console's cookie session (a different origin can't send our
httpOnly session cookie). It authenticates instead with a long-lived, revocable bearer token
scoped to one business, generated once from the console and pasted into the extension's options
page. Only a sha256 hash is ever stored; the raw token is returned once, at creation time, and is
unrecoverable afterwards (same posture as a GitHub personal access token).

This is deliberately READ-ONLY and narrow: `ext_router.py` only exposes the pending-reply queue
through it, never write/approve/publish actions -- the human still posts the reply themselves on
the platform's own page.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

_PREFIX = "koobext_"


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_token(business_id: int, created_by: Optional[int], label: Optional[str] = None) -> dict:
    """Mint a new token. Returns the RAW token once -- callers must show/copy it immediately;
    it cannot be retrieved again (only the hash is persisted)."""
    raw = _PREFIX + secrets.token_urlsafe(32)
    with db() as conn:
        row = conn.execute(
            "INSERT INTO extension_tokens (business_id, token_hash, label, created_by) "
            "VALUES (%s,%s,%s,%s) RETURNING id, created_at",
            (business_id, _hash(raw), (label or "Reply Assist extension").strip()[:200], created_by),
        ).fetchone()
        conn.commit()
    return {"id": int(row["id"]), "token": raw, "created_at": row["created_at"]}


def list_tokens(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, label, created_at, last_used_at, revoked_at FROM extension_tokens "
            "WHERE business_id=%s ORDER BY id DESC", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def revoke_token(token_id: int, business_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "UPDATE extension_tokens SET revoked_at=now() WHERE id=%s AND business_id=%s "
            "AND revoked_at IS NULL RETURNING id", (token_id, business_id)).fetchone()
        conn.commit()
    return bool(row)


def resolve_business(raw_token: str) -> Optional[int]:
    """Validate a raw bearer token from the extension -> the business_id it's scoped to, or None
    if unknown/revoked. Touches last_used_at (best-effort, non-fatal on failure)."""
    if not raw_token or not raw_token.startswith(_PREFIX):
        return None
    with db() as conn:
        row = conn.execute(
            "SELECT id, business_id FROM extension_tokens WHERE token_hash=%s AND revoked_at IS NULL",
            (_hash(raw_token),)).fetchone()
        if not row:
            return None
        try:
            conn.execute("UPDATE extension_tokens SET last_used_at=now() WHERE id=%s", (row["id"],))
            conn.commit()
        except Exception:  # noqa: BLE001 -- last_used_at is best-effort telemetry, never block auth
            pass
    return int(row["business_id"])
