"""
HeyGen avatar-video renderer — real explainer videos from a vetted script
=========================================================================
Turns a compliance-vetted explainer SCRIPT's narration into a rendered talking-head MP4 (+ built-in
SRT captions) via the HeyGen API. Chosen over Veo/Sora (2026 provider research) for one decisive
reason: HeyGen speaks the EXACT vetted script VERBATIM, while Veo/Sora *generate* narration from a
prompt — a hallucination/unverified-claims risk that is a brand-safety liability for regulated
financial content. HeyGen is deterministic, brand-safe, arbitrary-length from the script, returns
captions, and is PAYG (~$3-4/min, no monthly commitment). Sora's video API is being removed
(2026-09-24), so it is not an option.

Dormant-safe: no-ops (returns {skipped}) without HEYGEN_API_KEY + HEYGEN_AVATAR_ID. All network I/O
is host-pinned + SSRF-guarded. Targets the stable v2 generate + v1 status endpoints (supported through
2026-10-31); override HEYGEN_GEN_URL / HEYGEN_STATUS_URL for the v3 surface if desired.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

try:
    from . import http as _http
    from . import content_quality as _cq
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore
    import content_quality as _cq  # type: ignore

log = logging.getLogger("heygen")

_API_BASE = os.getenv("HEYGEN_API_BASE", "https://api.heygen.com")
_GEN_URL = os.getenv("HEYGEN_GEN_URL", f"{_API_BASE}/v2/video/generate")
_STATUS_URL = os.getenv("HEYGEN_STATUS_URL", f"{_API_BASE}/v1/video_status.get")
_MAX_POLLS = int(os.getenv("HEYGEN_MAX_POLLS", "90"))       # ~15 min at 10s
_POLL_SECONDS = int(os.getenv("HEYGEN_POLL_SECONDS", "10"))
_MAX_CHARS = int(os.getenv("HEYGEN_MAX_SCRIPT_CHARS", "1500"))  # ~2 min of narration (retention cliff)


def configured() -> bool:
    """A key AND a chosen avatar are both required — HeyGen has no default avatar."""
    return bool(os.getenv("HEYGEN_API_KEY") and os.getenv("HEYGEN_AVATAR_ID"))


def _key() -> str:
    return os.getenv("HEYGEN_API_KEY", "")


def narration_from_script(script: str) -> str:
    """The SPOKEN words only — exactly what the avatar should say. Strips [stage directions],
    (On-screen: ...) cues, ## headings, speaker labels (via content_quality._spoken_only) and the
    [m:ss] timestamps, then collapses whitespace."""
    spoken = _cq._spoken_only(script or "")
    spoken = re.sub(r"\[?\d{1,2}:[0-5]\d\]?", " ", spoken)          # timestamps
    spoken = re.sub(r"^\s*[-*#>|].*$", " ", spoken, flags=re.M)     # any residual list/heading lines
    return re.sub(r"\s+", " ", spoken).strip()


def _download_binary(uri: str, *, timeout: int = 180) -> Optional[bytes]:
    """SSRF-guarded binary download of HeyGen's rendered-video / caption URL (a signed CDN URL — no
    auth header). allow_redirects=False + strict 200 gate so a redirect stub is never persisted as an
    mp4."""
    try:
        from . import netguard as _ng
    except ImportError:  # pragma: no cover
        import netguard as _ng  # type: ignore
    try:
        _ng.assert_url_allowed(uri)
    except Exception as e:  # noqa: BLE001 -- UnsafeURLError
        log.warning("heygen: asset uri blocked by SSRF guard: %s", e)
        return None
    import requests
    try:
        r = requests.get(uri, timeout=timeout, allow_redirects=False)
        return r.content if r.status_code == 200 else None
    except Exception as e:  # noqa: BLE001
        log.warning("heygen: asset download failed: %s", e)
        return None


def render(business_id: int, script: str, *, title: str = "", work_order_id: Optional[int] = None,
           draft_id: Optional[int] = None, avatar_id: Optional[str] = None,
           voice_id: Optional[str] = None, aspect: str = "16:9") -> dict:
    """Render a script's narration into a talking-head MP4 + SRT via HeyGen and store it as a `video`
    visual_asset (so the Media UI's player + the YouTube publisher can use it). Returns
    {ok, visual_id, video_url, srt, duration, file_path} or {skipped}/{ok:False, error}. Never raises."""
    if not configured():
        return {"skipped": True,
                "reason": "HeyGen not configured (set HEYGEN_API_KEY + HEYGEN_AVATAR_ID; optional HEYGEN_VOICE_ID)"}
    narration = narration_from_script(script)[:_MAX_CHARS]
    if not narration:
        return {"ok": False, "error": "no narration text found in the script"}
    avatar = avatar_id or os.getenv("HEYGEN_AVATAR_ID", "")
    voice = voice_id or os.getenv("HEYGEN_VOICE_ID", "")
    w, h = (720, 1280) if aspect == "9:16" else (1280, 720)
    voice_obj: dict = {"type": "text", "input_text": narration}
    if voice:
        voice_obj["voice_id"] = voice
    body = {
        "video_inputs": [{
            "character": {"type": "avatar", "avatar_id": avatar, "avatar_style": "normal"},
            "voice": voice_obj,
            "background": {"type": "color", "value": os.getenv("HEYGEN_BG_COLOR", "#0b1020")},
        }],
        "dimension": {"width": w, "height": h},
        "caption": True,
        "title": (title or "Explainer video")[:100],
    }
    hdr = {"X-Api-Key": _key(), "Content-Type": "application/json"}
    start = _http.request_json("POST", _GEN_URL, headers=hdr, json=body, timeout=60,
                               max_retries=2, guard_redirects=True)
    if start.failed or not isinstance(start.data, dict):
        return {"ok": False, "error": start.error or "HeyGen generate call failed"}
    data = start.data.get("data") if isinstance(start.data.get("data"), dict) else start.data
    vid_id = data.get("video_id") or start.data.get("video_id")
    if not vid_id:
        return {"ok": False, "error": f"HeyGen returned no video_id: {str(start.data)[:200]}"}

    video_url = srt_url = None
    duration = None
    for _ in range(_MAX_POLLS):
        time.sleep(_POLL_SECONDS)
        st = _http.request_json("GET", f"{_STATUS_URL}?video_id={vid_id}", headers=hdr,
                                timeout=30, max_retries=2, guard_redirects=True)
        if st.failed or not isinstance(st.data, dict):
            continue
        d = st.data.get("data") or {}
        status = (d.get("status") or "").lower()
        if status in ("completed", "success", "done"):
            video_url = d.get("video_url") or d.get("video_url_caption")
            srt_url = d.get("subtitle_url") or d.get("caption_url") or d.get("srt_url")
            duration = d.get("duration")
            break
        if status in ("failed", "error"):
            return {"ok": False, "error": f"HeyGen render failed: {d.get('error') or str(d)[:200]}"}
    if not video_url:
        return {"ok": False, "error": "HeyGen render timed out or returned no video_url"}

    raw = _download_binary(video_url)
    if not raw:
        return {"ok": False, "error": "could not download the rendered HeyGen video"}
    srt = ""
    if srt_url:
        srt_bytes = _download_binary(srt_url, timeout=60)
        srt = srt_bytes.decode("utf-8", "replace") if srt_bytes else ""

    try:
        from . import visual_content as _vc
    except ImportError:  # pragma: no cover
        import visual_content as _vc  # type: ignore
    path = _vc._save_png(business_id, raw, ext="mp4")
    visual_id = _vc._persist(
        business_id, kind="video", provider="heygen", model=os.getenv("HEYGEN_ENGINE", "avatar"),
        prompt=narration[:500], file_path=path, url=video_url,
        compliance_note="Avatar speaks the vetted script verbatim (no generated/hallucinated speech).",
        work_order_id=work_order_id, draft_id=draft_id, file_bytes=raw, mime="video/mp4",
        meta={"source": "heygen", "srt": srt, "duration": duration, "narration_chars": len(narration)})
    try:  # itemized cost — HeyGen bills per second (~$0.05-0.067/s); estimate from duration/speech rate
        from . import cost as _cost
        secs = float(duration or 0) or (len(narration) / 14.0)   # ~14 chars/sec of speech
        _cost.record_cost(business_id, None, "video", "heygen", "render_explainer",
                          units=secs, unit_label="seconds", model="avatar",
                          detail={"content_type": "video", "api": "heygen"})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "visual_id": visual_id, "video_url": video_url, "srt": srt,
            "duration": duration, "file_path": path}
