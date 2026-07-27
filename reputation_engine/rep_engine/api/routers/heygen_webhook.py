"""
Public inbound webhook — HeyGen Video Agent render-completion callback
======================================================================
HeyGen POSTs here (the `callback_url` we set on POST /v3/video-agents) when a produced render
completes or fails. The payload is used only as a NUDGE — the completion sweep re-checks the
AUTHORITATIVE session status via the API — so this is robust to the exact webhook payload shape.
`callback_id` encodes 'business_id:draft_id:signature'.

No auth (HeyGen can't carry our bearer). Safe: the handler only enqueues the completion sweep for a
business, which can only finish renders that ALREADY exist as `rendering` in our DB — an arbitrary
POST just triggers a cheap no-op sweep. The path is CSRF-exempt (registered in main.py).
"""

from __future__ import annotations

import logging
import hashlib
import hmac
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("api.heygen_webhook")
router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/heygen")
async def heygen_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    cid = str((data or {}).get("callback_id") or body.get("callback_id") or "")
    business_id = None
    secret = os.getenv("HEYGEN_WEBHOOK_SECRET", "").strip()
    parts = cid.split(":")
    if not secret:
        return JSONResponse({"ok": True, "ignored": "webhook secret not configured"})
    if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
        raw = f"{parts[0]}:{parts[1]}"
        expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(expected, parts[2]):
            business_id = int(parts[0])
    if business_id is None:
        return JSONResponse({"ok": True, "ignored": "invalid callback_id"})
    try:
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, "poll_video_renders", args={})   # worker completes it (download+store)
    except Exception as e:  # noqa: BLE001
        log.warning("heygen webhook: enqueue sweep failed: %s", e)
    return JSONResponse({"ok": True})
