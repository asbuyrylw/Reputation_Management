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
  - Keyless-safe: a no-op until WEBHOOK_URL is set, so nothing breaks without configuration
    (same posture as Stripe/Serper).
  - SSRF-guarded: the target URL is checked with netguard.assert_url_allowed and redirects are
    refused, so a misconfigured/hostile URL can't reach internal/metadata addresses.
  - Signed: when WEBHOOK_SECRET is set, an `X-Webhook-Signature: sha256=<hmac>` header signs the
    EXACT bytes sent, so the receiver can verify authenticity.

Env:
  WEBHOOK_URL      a single outbound endpoint (per-business routing can come later via
                   integration_settings); unset => disabled.
  WEBHOOK_SECRET   optional HMAC-SHA256 signing key for X-Webhook-Signature.
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
except ImportError:  # pragma: no cover -- loose-script fallback
    import netguard as _netguard  # type: ignore

log = logging.getLogger("rep_engine.webhooks")


# Refuse redirects so a 3xx can't bounce a guarded URL to an internal address (SSRF defense).
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401, ANN001
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def enabled() -> bool:
    return bool(os.getenv("WEBHOOK_URL", "").strip())


def _targets(business_id: int) -> list[str]:
    # v1: a single global endpoint. Per-business routing (integration_settings) is a later add.
    g = os.getenv("WEBHOOK_URL", "").strip()
    return [g] if g else []


def emit(business_id: int, event: str, data: dict) -> None:
    """Best-effort POST of {event, business_id, data} to the configured webhook target(s).
    No-op when unconfigured. Never raises -- a webhook problem must not affect the caller."""
    urls = _targets(business_id)
    if not urls:
        return
    body = {"event": event, "business_id": business_id, "data": data}
    try:
        raw = json.dumps(body, default=str).encode("utf-8")
    except Exception as e:  # noqa: BLE001 -- unserializable payload must not break the caller
        log.debug("webhook payload not serializable for %s: %s", event, e)
        return
    headers = {"Content-Type": "application/json", "User-Agent": "ReputationConsole-Webhook/1"}
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if secret:
        headers["X-Webhook-Signature"] = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    for url in urls:
        try:
            _netguard.assert_url_allowed(url)   # SSRF guard on the (tenant-supplied) target
            req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
            with _opener.open(req, timeout=10) as r:
                r.read(1)                        # we don't need the body; just complete the call
        except Exception as e:  # noqa: BLE001 -- webhooks are fire-and-forget
            log.debug("webhook emit (%s) to %s failed: %s", event, url, e)
