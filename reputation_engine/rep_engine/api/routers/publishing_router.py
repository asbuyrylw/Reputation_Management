"""Publishing API (Integrations Phase 2).

Read publish targets for an asset; enqueue a publish (network-grain targets + publish_sweep drain,
never inline I/O); retry a failed target. Writes require editor access.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, get_current_user, require_business_editor

try:
    from ...publishing import runner as _runner, registry as _registry
except ImportError:  # pragma: no cover
    from publishing import runner as _runner, registry as _registry  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["publishing"])

# Human-friendly channel labels for the picker.
_CHANNEL_LABELS = {
    "wp_blog": "WordPress blog",
    "social_fb_page": "Facebook page", "social_ig": "Instagram", "social_li_org": "LinkedIn",
    "social_x": "X (Twitter)", "social_pinterest": "Pinterest", "gbp_post": "Google Business post",
}


class PublishRequest(BaseModel):
    channels: list[str]
    scheduled_for: Optional[datetime] = None


@router.get("/publish-channels")
def publish_channels(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Which publish channels have a healthy connection (drives the ChannelPicker)."""
    out = []
    for ch in _registry.known_channels():
        kind = _registry.kind_for(ch)
        connected = False
        if kind:
            row = conn.execute(
                "SELECT 1 FROM platform_connections WHERE business_id=%s AND kind=%s AND status='active' LIMIT 1",
                (business_id, kind)).fetchone()
            connected = bool(row)
        out.append({"channel": ch, "label": _CHANNEL_LABELS.get(ch, ch), "kind": kind,
                    "connected": connected})
    return out


@router.get("/assets/{asset_id}/publish-targets")
def publish_targets(asset_id: int, business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, network, status, external_url, external_id, scheduled_for, "
        "published_at, attempts, last_error, updated_at FROM publish_targets "
        "WHERE business_id=%s AND asset_id=%s ORDER BY id", (business_id, asset_id)).fetchall()
    return [dict(r) for r in rows]


@router.post("/assets/{asset_id}/publish")
def publish_asset(asset_id: int, body: PublishRequest,
                  business_id: int = Depends(require_business_editor),
                  user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    a = conn.execute("SELECT id, compliance_pass FROM assets WHERE id=%s AND business_id=%s",
                     (asset_id, business_id)).fetchone()
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "asset not found")
    if not body.channels:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no channels selected")
    unknown = [c for c in body.channels if c not in _registry.known_channels()]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown channel(s): {', '.join(unknown)}")
    out = _runner.create_targets(business_id, asset_id, body.channels,
                                 created_by=user["id"], scheduled_for=body.scheduled_for)
    if out["created"]:
        try:
            from .. import jobs as _jobs
            _jobs.enqueue(business_id, "publish_sweep", requested_by=user["id"])
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, **out}


@router.post("/publish-targets/{target_id}/retry")
def retry_target(target_id: int, business_id: int = Depends(require_business_editor),
                 user: dict = Depends(get_current_user)):
    out = _runner.retry_target(business_id, target_id)
    if not out.get("ok"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "target not found or not retryable")
    try:
        from .. import jobs as _jobs
        _jobs.enqueue(business_id, "publish_sweep", requested_by=user["id"])
    except Exception:  # noqa: BLE001
        pass
    return out
