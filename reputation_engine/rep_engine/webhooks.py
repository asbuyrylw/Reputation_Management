"""
Outbound webhook bus -- the bridge out of the console into the client's stack.
==============================================================================
Every notification and every finished job can fan out to an external endpoint (GoHighLevel,
Zapier, Make, n8n, a custom receiver), so generated tasks, approved drafts, score drops,
incidents, and audit completions stop dead-ending in the console and instead drive the
client's existing automations.

Design:
  - ONE choke point: emit(business_id, event, data). Wired into notifications.notify() and
    jobs.run_job()'s terminal block. Best-effort -- a webhook failure NEVER affects the
    notification/job it rode on.
  - Keyless-safe: a no-op until a tenant webhook is set, so nothing breaks without configuration
    (same posture as Stripe/Serper). A legacy global endpoint is allowed only when explicitly enabled.
  - SSRF-guarded: the target URL is checked with netguard.assert_url_allowed and redirects are
    refused, so a misconfigured/hostile URL can't reach internal/metadata addresses.
  - Signed: when a tenant or legacy secret is set, an `X-Webhook-Signature: sha256=<hmac>` header
    signs the EXACT bytes sent, so the receiver can verify authenticity.

Env:
  WEBHOOK_URL      legacy global endpoint. Ignored unless WEBHOOK_ALLOW_GLOBAL=true.
  WEBHOOK_SECRET   optional HMAC-SHA256 signing key for the legacy endpoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request

try:
    from . import netguard as _netguard
    from .db import db
except ImportError:  # pragma: no cover -- loose-script fallback
    import netguard as _netguard  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("rep_engine.webhooks")


# Refuse redirects so a 3xx can't bounce a guarded URL to an internal address (SSRF defense).
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401, ANN001
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _global_allowed() -> bool:
    return os.getenv("WEBHOOK_ALLOW_GLOBAL", "").strip().lower() in ("1", "true", "yes")


def _targets(business_id: int) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT webhook_url, webhook_secret FROM integration_settings WHERE business_id=%s",
                (business_id,),
            ).fetchone()
        cfg = dict(row) if row else {}
        if (cfg.get("webhook_url") or "").strip():
            targets.append(((cfg.get("webhook_url") or "").strip(),
                            (cfg.get("webhook_secret") or "").strip()))
    except Exception as e:  # noqa: BLE001 -- absent columns/table means no tenant webhook
        log.debug("tenant webhook settings unavailable for business %s: %s", business_id, e)
    if _global_allowed():
        g = os.getenv("WEBHOOK_URL", "").strip()
        if g:
            targets.append((g, os.getenv("WEBHOOK_SECRET", "").strip()))
    return targets


def enabled(business_id: int | None = None) -> bool:
    if business_id is not None:
        return bool(_targets(business_id))
    return bool(_global_allowed() and os.getenv("WEBHOOK_URL", "").strip())


def emit(business_id: int, event: str, data: dict) -> None:
    """Best-effort POST of {event, business_id, data} to the configured webhook target(s).
    No-op when unconfigured. Never raises -- a webhook problem must not affect the caller."""
    targets = _targets(business_id)
    if not targets:
        return
    body = {"event": event, "business_id": business_id, "data": data}
    try:
        raw = json.dumps(body, default=str).encode("utf-8")
    except Exception as e:  # noqa: BLE001 -- unserializable payload must not break the caller
        log.debug("webhook payload not serializable for %s: %s", event, e)
        return
    headers = {"Content-Type": "application/json", "User-Agent": "ReputationConsole-Webhook/1"}
    for url, secret in targets:
        send_headers = dict(headers)
        if secret:
            send_headers["X-Webhook-Signature"] = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        try:
            _netguard.assert_url_allowed(url)   # SSRF guard on the (tenant-supplied) target
            req = urllib.request.Request(url, data=raw, headers=send_headers, method="POST")
            with _opener.open(req, timeout=10) as r:
                r.read(1)                        # we don't need the body; just complete the call
        except Exception as e:  # noqa: BLE001 -- webhooks are fire-and-forget
            log.debug("webhook emit (%s) to %s failed: %s", event, url, e)
