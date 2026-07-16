"""
YouTube publish orchestration — a rendered video asset → the owner's YouTube channel
====================================================================================
Ties together the connections vault (YouTube OAuth token), a rendered `video` visual_asset (bytes +
SRT + metadata), and the YouTube Data API client (connections/providers/youtube.py). YouTube is the
single most-cited domain in Google AI Overviews (via its captions), so publishing the rendered
explainer here is the last, highest-leverage step of the video citability loop.

Dormant-safe: returns {skipped} when no YouTube connection exists; the owner connects YouTube in
Integrations (a Google OAuth with the youtube.upload scope). Uploads as UNLISTED by default so a human
flips it public. Never raises.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

try:
    from .db import db
    from . import visual_content as _vc
    from .connections import vault as _vault
    from .connections.providers import youtube as _yt
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import visual_content as _vc  # type: ignore
    from connections import vault as _vault  # type: ignore
    from connections.providers import youtube as _yt  # type: ignore

log = logging.getLogger("youtube_publish")


def _find_connection(business_id: int) -> Optional[int]:
    """The business's active YouTube connection id, if any."""
    for c in _vault.list_connections(business_id):
        if c.get("kind") == "youtube" and (c.get("status") in ("active", "connected", None)):
            return c["id"]
    return None


def _fresh_token(conn_id: int, business_id: int, creds: dict) -> str:
    """The access token, refreshed in-process if it's already expired (persistence is handled
    separately by the vault refresh drain; this just avoids a guaranteed-401 upload)."""
    token = creds.get("access_token") or ""
    exp = creds.get("expires_at")
    if exp and isinstance(exp, datetime) and exp <= datetime.now(timezone.utc):
        rf = _yt.refresh(creds)
        if rf.get("ok") and rf.get("access_token"):
            token = rf["access_token"]
    return token


def publish_video(business_id: int, visual_id: int, *, privacy: str = "unlisted",
                  title: Optional[str] = None, description: Optional[str] = None) -> dict:
    """Upload a rendered `video` visual_asset to the owner's YouTube channel with its SRT captions +
    a rich description. Records the YouTube URL back on the asset's meta. Returns {ok, url, video_id}
    or {skipped}/{ok:False, error}. Never raises."""
    conn_id = _find_connection(business_id)
    if not conn_id:
        return {"skipped": True,
                "reason": "no YouTube connection — connect YouTube in Integrations (Google OAuth, youtube.upload scope)"}
    creds = _vault.credentials(conn_id, business_id)
    if not creds or not creds.get("access_token"):
        return {"ok": False, "error": "the YouTube connection has no token — reconnect it"}
    blob = _vc.visual_file_blob(visual_id, business_id)
    if not blob:
        return {"ok": False, "error": "rendered video not found (or has no stored bytes)"}
    video_bytes, _mime = blob
    with db() as c:
        row = c.execute("SELECT prompt, meta FROM visual_assets WHERE id=%s AND business_id=%s AND kind='video'",
                        (visual_id, business_id)).fetchone()
    if not row:
        return {"ok": False, "error": f"visual {visual_id} is not a video asset for this business"}
    meta = row.get("meta") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:  # noqa: BLE001
            meta = {}
    srt = (meta.get("srt") or "") if isinstance(meta, dict) else ""
    vtitle = title or (meta.get("title") if isinstance(meta, dict) else None) or "Explainer video"
    vdesc = description or row.get("prompt") or ""

    token = _fresh_token(conn_id, business_id, creds)
    res = _yt.upload_video(token, video_bytes, title=vtitle, description=vdesc, privacy=privacy)
    if not res.get("ok"):
        # A runtime auth rejection (401/403) must surface 'reconnect' like every other publish path,
        # else the connection stays 'active' and every subsequent publish 401s silently.
        if res.get("auth_failed"):
            try:
                _vault.revoke_on_runtime_401(conn_id, business_id, res.get("error"))
            except Exception:  # noqa: BLE001
                pass
        return res
    video_id, url = res["video_id"], res["url"]
    caption_ok = None
    if srt.strip():
        cap = _yt.insert_captions(token, video_id, srt)
        caption_ok = bool(cap.get("ok"))
    # record the published URL on the asset
    try:
        if isinstance(meta, dict):
            meta["youtube"] = {"video_id": video_id, "url": url, "privacy": privacy, "captions": caption_ok}
            with db() as c:
                c.execute("UPDATE visual_assets SET meta=%s WHERE id=%s AND business_id=%s",
                          (json.dumps(meta), visual_id, business_id))
                c.commit()
    except Exception as e:  # noqa: BLE001
        log.debug("could not record youtube url on visual %s: %s", visual_id, e)
    log.info("published visual %s to YouTube: %s (captions=%s)", visual_id, url, caption_ok)
    return {"ok": True, "video_id": video_id, "url": url, "privacy": privacy, "captions": caption_ok}
