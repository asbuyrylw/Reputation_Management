"""
Publish drain + target creation (Integrations Phase 2)
======================================================
The only DB-touching piece of the publishing layer. `drain(business_id)` claims every due
network-grain target for the business (one at a time, SKIP LOCKED), decrypts the connection via
the vault, calls the stateless adapter, and writes back a REDACTED `publish_attempts` row plus the
live URL onto `assets`. Connection-health is part of the claim; a runtime 401 revokes the
connection and strands its dependent targets. Exactly-once lives on the target's status claim.

`create_targets()` is called at content-approve time (or by the manual publish endpoint) to insert
one target per channel/network up front -- never a NULL-network parent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from ..db import db
    from ..connections import vault as _vault
    from ..integration_flags import redact as _redact
    from . import registry
    from .base import Connection, PublishPayload, PublishResult
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from connections import vault as _vault  # type: ignore
    from integration_flags import redact as _redact  # type: ignore
    from publishing import registry  # type: ignore
    from publishing.base import Connection, PublishPayload, PublishResult  # type: ignore

from psycopg.types.json import Json

log = logging.getLogger("publishing.runner")

_MAX_ATTEMPTS = 5
_BACKOFF_S = {1: 60, 2: 300, 3: 1800, 4: 7200}  # attempt# -> seconds until next try
# Provider kinds whose auth lives in an account-level env key (not a per-connection token), so a
# stored connection legitimately has no access_token and must not be force-revoked for lacking one.
_KEYLESS_KINDS = {"zernia"}


# ---------------------------------------------------------------------------
# Target creation (called at approve / manual publish; no I/O)
# ---------------------------------------------------------------------------
def create_targets(business_id: int, asset_id: int, channels: list[str], *,
                   work_order_id: Optional[int] = None, created_by: Optional[int] = None,
                   scheduled_for: Optional[datetime] = None) -> dict:
    """Insert one publish_targets row per channel that has a healthy connection. Channels with no
    healthy connection are SKIPPED (the asset stays manual) -- never a 409. Returns
    {created:[ids], skipped:[channels]}."""
    created: list[int] = []
    skipped: list[str] = []
    with db() as conn:
        for channel in channels:
            kind = registry.kind_for(channel)
            if not kind:
                skipped.append(channel)
                continue
            row = conn.execute(
                "SELECT id FROM platform_connections WHERE business_id=%s AND kind=%s "
                "AND status='active' ORDER BY id DESC LIMIT 1", (business_id, kind)).fetchone()
            if not row:
                skipped.append(channel)
                continue
            conn_id = row["id"]
            network = registry.network_for(channel)
            idem = f"{asset_id}:{conn_id}:{network}"
            status = "scheduled" if scheduled_for else "queued"
            payload_kind = "social" if registry.is_social(channel) else "article"
            ins = conn.execute(
                "INSERT INTO publish_targets (business_id, asset_id, connection_id, work_order_id, "
                " channel, network, payload_kind, status, idempotency_key, scheduled_for, "
                " next_attempt_at, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                (business_id, asset_id, conn_id, work_order_id, channel, network, payload_kind,
                 status, idem, scheduled_for, scheduled_for, created_by)).fetchone()
            if ins:
                created.append(ins["id"])
        conn.commit()
    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# The drain
# ---------------------------------------------------------------------------
def drain(business_id: int) -> dict:
    """Claim + publish every due target for the business. Returns a summary."""
    published = scheduled = failed = skipped = 0
    while True:
        target = _claim(business_id)
        if not target:
            break
        outcome = _process(business_id, target)
        published += outcome == "live"
        scheduled += outcome == "scheduled"
        failed += outcome == "failed"
        skipped += outcome == "skipped"
    return {"published": published, "scheduled": scheduled, "failed": failed, "skipped": skipped}


def _claim(business_id: int) -> Optional[dict]:
    """Atomically claim one due target whose connection is active. Releases the row lock by
    committing before the slow network I/O happens."""
    with db() as conn:
        row = conn.execute(
            "UPDATE publish_targets SET status='publishing', attempts=attempts+1, updated_at=now() "
            "WHERE id = ("
            "  SELECT pt.id FROM publish_targets pt "
            "  WHERE pt.business_id=%s AND pt.status IN ('queued','failed','scheduled') "
            "    AND (pt.next_attempt_at IS NULL OR pt.next_attempt_at <= now()) "
            "    AND pt.connection_id IN (SELECT id FROM platform_connections "
            "                             WHERE business_id=%s AND status='active') "
            "  ORDER BY pt.next_attempt_at NULLS FIRST, pt.id "
            "  FOR UPDATE SKIP LOCKED LIMIT 1) "
            "RETURNING *", (business_id, business_id)).fetchone()
        conn.commit()
    return dict(row) if row else None


def _process(business_id: int, target: dict) -> str:
    tid = target["id"]
    # Idempotency short-circuit: already posted -> mark live, don't double-post.
    if target.get("external_id"):
        _finalize(tid, business_id, "live", external_url=target.get("external_url"),
                  external_id=target.get("external_id"))
        return "skipped"

    payload, asset = _load_payload(business_id, target)
    if payload is None:
        _fail(tid, business_id, "asset missing/unreadable", retryable=False)
        return "failed"
    # Compliance re-gate: the runner trusts a human approval, but still refuses content that is
    # not strictly compliance-cleared (False or NULL).
    if asset.get("compliance_pass") is not True:
        _finalize(tid, business_id, "skipped", error="content not compliance-cleared for auto-post")
        return "skipped"

    creds = _vault.credentials(target["connection_id"], business_id)
    # Keyless social providers (Zernio) authenticate with an account-level env key, not a
    # per-connection token -- their row legitimately stores no access_token (only a profile id +
    # accounts map in meta). Requiring access_token here would force-revoke a perfectly healthy
    # Zernia connection on the first drain, so skip the secret check for keyless kinds.
    keyless = bool(creds) and creds.get("kind") in _KEYLESS_KINDS
    if not creds or (not keyless and not creds.get("access_token")):
        _vault.revoke_on_runtime_401(target["connection_id"], business_id, "missing credential")
        _set_status(tid, business_id, "needs_reconnect", "connection missing/unhealthy")
        return "failed"

    # Shared-platform quota guard (item 22): defer (don't fail) when the account-level provider cap
    # is reached, so a busy day across all tenants can't blow the API limit mid-campaign.
    try:
        from .. import quota as _quota
        if not _quota.channel_within_quota(target["channel"]):
            _retry_later(tid, business_id, target.get("attempts") or 1,
                         PublishResult(status="failed", error="platform daily quota reached -- deferred",
                                       retryable=True, retry_after_s=3600))
            return "failed"
    except Exception:  # noqa: BLE001 -- quota accounting must never block a publish on its own error
        pass

    conn_obj = _to_connection(creds, target["channel"])
    adapter = registry.adapter_for(target["channel"])
    if adapter is None:
        _fail(tid, business_id, f"no adapter for channel {target['channel']}", retryable=False)
        return "failed"
    try:
        result: PublishResult = adapter.publish(conn_obj, payload)
    except Exception as e:  # noqa: BLE001 -- an adapter bug must not wedge the drain
        result = PublishResult(status="failed", error=str(e), retryable=True)

    _record_attempt(tid, business_id, target.get("attempts"), result)

    if result.status in ("live", "scheduled"):
        _finalize(tid, business_id, result.status, external_url=result.external_url,
                  external_id=result.external_id, asset_id=target["asset_id"])
        return result.status
    # Failure branches
    if result.auth_failed:
        _vault.revoke_on_runtime_401(target["connection_id"], business_id, result.error)
        _set_status(tid, business_id, "needs_reconnect", result.error)
        return "failed"
    if result.retryable and (target.get("attempts") or 1) < _MAX_ATTEMPTS:
        _retry_later(tid, business_id, target.get("attempts") or 1, result)
        return "failed"
    _fail(tid, business_id, result.error or "publish failed", retryable=False)
    _notify_failed(business_id, target)
    return "failed"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_payload(business_id: int, target: dict):
    """Build the PublishPayload from the asset + its source draft body."""
    with db() as conn:
        asset = conn.execute(
            "SELECT id, title, summary, meta, compliance_pass, published_url, published_status "
            "FROM assets WHERE id=%s AND business_id=%s",
            (target["asset_id"], business_id)).fetchone()
        if not asset:
            return None, {}
        body = ""
        meta = asset.get("meta") or {}
        from_draft = meta.get("from_draft") if isinstance(meta, dict) else None
        if from_draft:
            d = conn.execute("SELECT body FROM content_drafts WHERE id=%s AND business_id=%s",
                            (from_draft, business_id)).fetchone()
            body = (d or {}).get("body") or ""
    scheduled_at = None
    if target.get("scheduled_for"):
        sf = target["scheduled_for"]
        scheduled_at = sf.astimezone(timezone.utc).isoformat() if isinstance(sf, datetime) else str(sf)
    if (target.get("payload_kind") or "article") == "social" or registry.is_social(target.get("channel") or ""):
        # Social/GBP posts carry short text + a link to the canonical article (amplification),
        # not the full article body.
        link = (asset.get("published_url") or "")
        text = (asset.get("summary") or asset.get("title") or "").strip()
        payload = PublishPayload(
            kind="social", text=text, link_url=link or None,
            network=target.get("network") or "_",
            idempotency_key=target.get("idempotency_key") or "", scheduled_at=scheduled_at)
    else:
        payload = PublishPayload(
            kind="article", title=asset.get("title"), body_markdown=body,
            network=target.get("network") or "_",
            idempotency_key=target.get("idempotency_key") or "", scheduled_at=scheduled_at)
    return payload, dict(asset)


def _to_connection(creds: dict, channel: str) -> Connection:
    kind = creds["kind"]
    provider = {"wordpress_org": "wordpress", "google_business_profile": "google_business",
                "ayrshare_profile": "ayrshare"}.get(kind, kind)
    cfg = dict(creds.get("meta") or {})
    cfg["profile_key"] = creds.get("access_token") if kind == "ayrshare_profile" else cfg.get("profile_key")
    cfg["location_id"] = creds.get("profile_ref")
    cfg["account_id"] = creds.get("account_ref")
    return Connection(id=creds["id"], business_id=creds["business_id"], provider=provider,
                      channel=channel, access_token=creds.get("access_token") or "",
                      refresh_token=creds.get("refresh_token"), config=cfg)


def _finalize(tid: int, business_id: int, status: str, *, external_url=None, external_id=None,
              asset_id: Optional[int] = None, error: Optional[str] = None) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE publish_targets SET status=%s, external_url=COALESCE(%s, external_url), "
            "external_id=COALESCE(%s, external_id), published_at=CASE WHEN %s='live' THEN now() "
            "ELSE published_at END, last_error=%s, next_attempt_at=NULL, updated_at=now() "
            "WHERE id=%s AND business_id=%s",
            (status, external_url, external_id, status, _redact(error), tid, business_id))
        # Write the canonical live URL back onto the asset (article target only).
        if status == "live" and asset_id and external_url:
            conn.execute(
                "UPDATE assets SET published_url=%s, published_status='live', published_at=now() "
                "WHERE id=%s AND business_id=%s", (external_url, asset_id, business_id))
        conn.commit()


def _retry_later(tid: int, business_id: int, attempt_no: int, result: PublishResult) -> None:
    delay = result.retry_after_s or _BACKOFF_S.get(attempt_no, 7200)
    nxt = datetime.now(timezone.utc) + timedelta(seconds=delay)
    with db() as conn:
        conn.execute(
            "UPDATE publish_targets SET status='failed', next_attempt_at=%s, last_error=%s, "
            "updated_at=now() WHERE id=%s AND business_id=%s",
            (nxt, _redact(result.error), tid, business_id))
        conn.commit()


def _fail(tid: int, business_id: int, error: str, *, retryable: bool) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE publish_targets SET status='failed', next_attempt_at=NULL, last_error=%s, "
            "updated_at=now() WHERE id=%s AND business_id=%s", (_redact(error), tid, business_id))
        conn.commit()


def _set_status(tid: int, business_id: int, status: str, error: Optional[str]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE publish_targets SET status=%s, last_error=%s, updated_at=now() "
            "WHERE id=%s AND business_id=%s", (status, _redact(error), tid, business_id))
        conn.commit()


def _record_attempt(tid: int, business_id: int, attempt_no, result: PublishResult) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO publish_attempts (target_id, business_id, attempt_no, ok, http_status, "
            " external_id, external_url, response_summary, error, retryable) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (tid, business_id, attempt_no, result.status in ("live", "scheduled"),
             result.http_status, result.external_id, result.external_url,
             Json(_redact({"status": result.status})), _redact(result.error), result.retryable))
        conn.commit()


def _notify_failed(business_id: int, target: dict) -> None:
    try:
        from ..notifications import notify
        notify(business_id, "publish_failed", "A publish didn't go through",
               "We couldn't publish an approved piece to a connected channel. You can retry it from "
               "the asset, or post it manually.", severity="warning",
               dedup_key=f"publish-failed:{target['id']}")
    except Exception:  # noqa: BLE001
        pass


def retry_target(business_id: int, target_id: int) -> dict:
    """Manual retry: reset a failed/needs_reconnect target to queued (re-drains on next sweep)."""
    with db() as conn:
        row = conn.execute(
            "UPDATE publish_targets SET status='queued', next_attempt_at=NULL, last_error=NULL, "
            "updated_at=now() WHERE id=%s AND business_id=%s AND status IN "
            "('failed','needs_reconnect','skipped','canceled') RETURNING id",
            (target_id, business_id)).fetchone()
        conn.commit()
    return {"ok": bool(row), "id": target_id}
