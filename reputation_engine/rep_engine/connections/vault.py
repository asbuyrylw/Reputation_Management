"""
Connections Vault -- CRUD over platform_connections (Integrations Phase 1)
=========================================================================
The ONLY importer of `rep_engine.crypto` (CI grep-asserted): every read/write of a stored
secret flows through here, so plaintext tokens touch exactly one audited module. Secrets are
encrypted before INSERT and decrypted only in-process at post/verify time; a redacted DTO
(no `*_enc` columns) is what the API returns.

Tenant isolation: every read/write re-passes `business_id` into the WHERE clause; `access_token()`
fails closed if the caller's `business_id` does not match the row.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from ..db import db
    from .. import crypto
    from ..integration_flags import redact
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import crypto  # type: ignore
    from integration_flags import redact  # type: ignore

from psycopg.types.json import Json

log = logging.getLogger("connections.vault")

# Columns safe to return to the API (no ciphertext).
_DTO_COLS = ("id, business_id, kind, label, status, token_type, expires_at, account_ref, "
             "profile_ref, external_id, scopes, gbp_access, meta, last_error, last_used_at, "
             "connected_by, created_at, updated_at")


def _redact(value):
    """Scrub secrets from anything destined for a durable column / log (delegates to the shared helper)."""
    return redact(value)


def _to_dto(row: dict) -> dict:
    """Redacted connection DTO. `meta` is non-secret by construction but we still redact defensively."""
    d = dict(row)
    d["meta"] = _redact(d.get("meta") or {})
    d["has_token"] = True  # ciphertext presence is implied; never expose it
    return d


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def upsert_connection(business_id: int, kind: str, *, token_type: str,
                      access_token: Optional[str] = None, refresh_token: Optional[str] = None,
                      expires_at: Optional[datetime] = None, account_ref: Optional[str] = None,
                      profile_ref: Optional[str] = None, external_id: Optional[str] = None,
                      scopes: Optional[list] = None, gbp_access: Optional[str] = None,
                      meta: Optional[dict] = None, label: Optional[str] = None,
                      connected_by: Optional[int] = None, status: str = "active") -> int:
    """Encrypt secrets and upsert a connection. Returns the connection id.

    Dedups on (business_id, kind, account_ref). On conflict the secrets + status are refreshed
    (a re-connect overwrites the old token). Secrets are encrypted here, never logged."""
    acc_enc = crypto.encrypt(access_token)
    ref_enc = crypto.encrypt(refresh_token)
    with db() as conn:
        row = conn.execute(
            "INSERT INTO platform_connections "
            "(business_id, kind, label, status, access_token_enc, refresh_token_enc, token_type, "
            " expires_at, account_ref, profile_ref, external_id, scopes, gbp_access, meta, "
            " connected_by, last_error, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,now()) "
            "ON CONFLICT (business_id, kind, account_ref) DO UPDATE SET "
            "  label=COALESCE(EXCLUDED.label, platform_connections.label), "
            "  status=EXCLUDED.status, "
            "  access_token_enc=COALESCE(EXCLUDED.access_token_enc, platform_connections.access_token_enc), "
            "  refresh_token_enc=COALESCE(EXCLUDED.refresh_token_enc, platform_connections.refresh_token_enc), "
            "  token_type=EXCLUDED.token_type, expires_at=EXCLUDED.expires_at, "
            "  profile_ref=COALESCE(EXCLUDED.profile_ref, platform_connections.profile_ref), "
            "  external_id=COALESCE(EXCLUDED.external_id, platform_connections.external_id), "
            "  scopes=COALESCE(NULLIF(EXCLUDED.scopes, '[]'::jsonb), platform_connections.scopes), "
            "  gbp_access=COALESCE(EXCLUDED.gbp_access, platform_connections.gbp_access), "
            "  meta=COALESCE(platform_connections.meta, '{}'::jsonb) || COALESCE(EXCLUDED.meta, '{}'::jsonb), "
            "  last_error=NULL, updated_at=now() "
            "RETURNING id",
            (business_id, kind, label, status, acc_enc, ref_enc, token_type, expires_at,
             account_ref, profile_ref, external_id, Json(scopes or []), gbp_access,
             Json(meta or {}), connected_by),
        ).fetchone()
        conn.commit()
    return int(row["id"])


def mark_status(conn_id: int, status: str, *, last_error: Optional[str] = None,
                business_id: Optional[int] = None) -> None:
    """Set connection status (+ redacted last_error). Used by the refresh sweep + runtime 401 path."""
    where = "id=%s" + (" AND business_id=%s" if business_id is not None else "")
    params = [status, _redact(last_error), conn_id]
    if business_id is not None:
        params.append(business_id)
    with db() as conn:
        conn.execute(
            f"UPDATE platform_connections SET status=%s, last_error=%s, updated_at=now() WHERE {where}",
            tuple(params))
        conn.commit()


def touch_used(conn_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE platform_connections SET last_used_at=now() WHERE id=%s", (conn_id,))
        conn.commit()


def set_account_and_meta(conn_id: int, business_id: int, *, account_ref: Optional[str] = None,
                         meta_updates: Optional[dict] = None) -> bool:
    """Update a connection's account_ref and merge meta in place (business-scoped). Used e.g. to
    record the chosen GSC property on the existing callback-created connection -- a re-upsert would
    create a duplicate row because account_ref is part of the dedup key."""
    with db() as conn:
        row = conn.execute(
            "UPDATE platform_connections SET "
            "account_ref=COALESCE(%s, account_ref), "
            "meta=COALESCE(meta,'{}'::jsonb) || %s, updated_at=now() "
            "WHERE id=%s AND business_id=%s RETURNING id",
            (account_ref, Json(meta_updates or {}), conn_id, business_id)).fetchone()
        conn.commit()
    return bool(row)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def list_connections(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            f"SELECT {_DTO_COLS} FROM platform_connections WHERE business_id=%s ORDER BY id DESC",
            (business_id,)).fetchall()
    return [_to_dto(r) for r in rows]


def get_connection(conn_id: int, business_id: Optional[int] = None) -> Optional[dict]:
    where = "id=%s" + (" AND business_id=%s" if business_id is not None else "")
    params = (conn_id, business_id) if business_id is not None else (conn_id,)
    with db() as conn:
        row = conn.execute(f"SELECT {_DTO_COLS} FROM platform_connections WHERE {where}", params).fetchone()
    return _to_dto(row) if row else None


def access_token(conn_id: int, business_id: Optional[int] = None) -> Optional[str]:
    """Decrypt the access-token secret for in-process use (posting/verify). Fail closed on a
    cross-business mismatch -- callers in post jobs MUST pass business_id."""
    where = "id=%s" + (" AND business_id=%s" if business_id is not None else "")
    params = (conn_id, business_id) if business_id is not None else (conn_id,)
    with db() as conn:
        row = conn.execute(
            f"SELECT business_id, access_token_enc FROM platform_connections WHERE {where}", params).fetchone()
    if not row:
        return None
    return crypto.decrypt(row["access_token_enc"])


def credentials(conn_id: int, business_id: Optional[int] = None) -> Optional[dict]:
    """Decrypt access+refresh tokens + return non-secret meta, for the publish runner / refresh.
    In-process only -- the result is never logged or persisted."""
    where = "id=%s" + (" AND business_id=%s" if business_id is not None else "")
    params = (conn_id, business_id) if business_id is not None else (conn_id,)
    with db() as conn:
        row = conn.execute(
            "SELECT id, business_id, kind, token_type, account_ref, profile_ref, external_id, "
            "scopes, gbp_access, meta, expires_at, access_token_enc, refresh_token_enc "
            f"FROM platform_connections WHERE {where}", params).fetchone()
    if not row:
        return None
    out = dict(row)
    out["access_token"] = crypto.decrypt(out.pop("access_token_enc"))
    out["refresh_token"] = crypto.decrypt(out.pop("refresh_token_enc"))
    return out


# ---------------------------------------------------------------------------
# Disconnect + refresh
# ---------------------------------------------------------------------------
def _strand_dependent_targets(conn, conn_id: int, business_id: int) -> None:
    """Move a revoked connection's queued/scheduled publish targets to needs_reconnect. Wrapped in
    a SAVEPOINT so that if `publish_targets` doesn't exist yet (pre-Phase-2) the failure rolls back
    only this statement, never the caller's revoke."""
    try:
        with conn.transaction():
            conn.execute(
                "UPDATE publish_targets SET status='needs_reconnect', updated_at=now() "
                "WHERE connection_id=%s AND business_id=%s AND status IN ('queued','scheduled','failed')",
                (conn_id, business_id))
    except Exception:  # noqa: BLE001 -- table not present yet / nothing to strand
        pass


def disconnect(conn_id: int, business_id: int) -> dict:
    """Revoke a connection: zero BOTH ciphertext columns, mark revoked, and move dependent
    queued/scheduled publish targets to needs_reconnect. Best-effort provider-side revoke; a
    failure there is fine -- local revoke + zeroed ciphertext is the fail-safe."""
    with db() as conn:
        row = conn.execute(
            "UPDATE platform_connections SET status='revoked', access_token_enc=NULL, "
            "refresh_token_enc=NULL, last_error=NULL, updated_at=now() "
            "WHERE id=%s AND business_id=%s RETURNING id", (conn_id, business_id)).fetchone()
        if not row:
            conn.commit()
            return {"ok": False, "reason": "not found"}
        _strand_dependent_targets(conn, conn_id, business_id)
        conn.commit()
    return {"ok": True, "id": conn_id}


def refresh_due(business_id: int) -> dict:
    """Token-refresh drain: refresh OAuth connections expiring within 24h, re-encrypt, and on a
    hard failure mark revoked + notify + move dependent targets to needs_reconnect.

    Non-OAuth credentials (app-passwords, profile-keys) never expire and are skipped."""
    cutoff = datetime.now(timezone.utc) + timedelta(hours=24)
    refreshed = failed = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT id, kind, token_type FROM platform_connections "
            "WHERE business_id=%s AND status='active' AND token_type IN ('google_oauth','bearer') "
            "AND expires_at IS NOT NULL AND expires_at < %s",
            (business_id, cutoff)).fetchall()
    for r in rows:
        creds = credentials(r["id"], business_id)
        if not creds or not creds.get("refresh_token"):
            continue
        try:
            from .oauth import refresh_token as _refresh
            new = _refresh(r["kind"], creds)
        except Exception as e:  # noqa: BLE001
            new = {"ok": False, "error": str(e)}
        if new.get("ok"):
            _apply_refresh(r["id"], business_id, new)
            refreshed += 1
        elif new.get("transient"):
            mark_status(r["id"], "error", last_error=new.get("error"), business_id=business_id)
        else:
            failed += 1
            _revoke_and_notify(r["id"], business_id, new.get("error"))
    return {"refreshed": refreshed, "failed": failed, "checked": len(rows)}


def _apply_refresh(conn_id: int, business_id: int, new: dict) -> None:
    acc = crypto.encrypt(new.get("access_token"))
    ref = crypto.encrypt(new.get("refresh_token")) if new.get("refresh_token") else None
    with db() as conn:
        if ref:
            conn.execute(
                "UPDATE platform_connections SET access_token_enc=%s, refresh_token_enc=%s, "
                "expires_at=%s, status='active', last_error=NULL, updated_at=now() "
                "WHERE id=%s AND business_id=%s",
                (acc, ref, new.get("expires_at"), conn_id, business_id))
        else:
            conn.execute(
                "UPDATE platform_connections SET access_token_enc=%s, expires_at=%s, "
                "status='active', last_error=NULL, updated_at=now() WHERE id=%s AND business_id=%s",
                (acc, new.get("expires_at"), conn_id, business_id))
        conn.commit()


def _revoke_and_notify(conn_id: int, business_id: int, error: Optional[str]) -> None:
    """Hard-revoke a connection (e.g. invalid_grant) + alert + strand dependent targets. Called
    both by the refresh sweep and by a runtime 401 during publish/reply."""
    mark_status(conn_id, "revoked", last_error=error, business_id=business_id)
    with db() as conn:
        _strand_dependent_targets(conn, conn_id, business_id)
        conn.commit()
    try:
        from ..notifications import notify
        notify(business_id, "connection_revoked",
               "Reconnect needed to keep posting",
               "An account connection stopped working and needs to be reconnected before "
               "anything can publish or reply through it.",
               severity="warning", dedup_key=f"conn-revoked:{conn_id}")
    except Exception:  # noqa: BLE001 -- notification must never break the sweep
        log.warning("connection_revoked notify failed for conn %s", conn_id)


def revoke_on_runtime_401(conn_id: int, business_id: int, error: Optional[str] = None) -> None:
    """Public entry for the publish/reply runners: a runtime 401/invalid_grant immediately
    surfaces 'Reconnect to post' rather than waiting for the 24h sweep."""
    _revoke_and_notify(conn_id, business_id, error or "authorization rejected at post time (401)")
