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
# Validated defaults (a real render was produced with these on 2026-07-16), so only HEYGEN_API_KEY is
# required to go live; override via HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID for a different presenter/voice.
_DEFAULT_AVATAR = "Abigail_standing_office_front"        # professional office-setting presenter
_DEFAULT_VOICE = "97dd67ab8ce242b6a9e7689cb00c6414"      # clear English (female) voice


# v3 Video Agent (produced pipeline: avatar + B-roll + motion graphics + styled scenes from ONE
# structured prompt). Reachable via raw REST (verified against HeyGen's open-source CLI). ~20-45 min
# per render, so we poll on a long deadline. Overridable for a future webhook/callback flow.
_AGENT_CREATE = os.getenv("HEYGEN_AGENT_URL", f"{_API_BASE}/v3/video-agents")
_VIDEO_GET = f"{_API_BASE}/v3/videos"
_AGENT_MAX_POLLS = int(os.getenv("HEYGEN_AGENT_MAX_POLLS", "95"))       # ~48 min at 30s
_AGENT_POLL_SECONDS = int(os.getenv("HEYGEN_AGENT_POLL_SECONDS", "30"))
# HeyGen team's "catchall" style block (from the official Video Agent prompt guide) — clean corporate
# look that suits financial-services explainers.
_STYLE_CATCHALL = (
    "Use minimal, clean styled visuals. Blue, black, and white as the main colors. Leverage motion "
    "graphics as B-rolls and A-roll overlays for stats and key points. Use Stock Media for real-world "
    "footage (families, offices, Cincinnati). Include an intro sequence, an outro sequence, and chapter "
    "breaks using Motion Graphics.")


def configured() -> bool:
    """Only the API key is required — a validated default avatar + voice are used unless overridden."""
    return bool(os.getenv("HEYGEN_API_KEY"))


def _key() -> str:
    return os.getenv("HEYGEN_API_KEY", "")


def narration_from_script(script: str) -> str:
    """The SPOKEN words only — exactly what the avatar should say. Strips [stage directions],
    (On-screen: ...) cues, ## headings, speaker labels (via content_quality._spoken_only) and the
    [m:ss] timestamps, then collapses whitespace."""
    spoken = _cq._spoken_only(script or "")
    spoken = re.sub(r"\[?\d{1,2}:[0-5]\d\]?", " ", spoken)                    # timestamps
    # Strip only the leading list/heading MARKER, keep the line's text -- a video_script's talking
    # points are often bullets ('- helps you save'), and wiping the whole line emptied the narration.
    spoken = re.sub(r"^\s*(?:[-*>|]+|#{1,6})\s+", " ", spoken, flags=re.M)
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
        return {"skipped": True, "reason": "HeyGen not configured (set HEYGEN_API_KEY)"}
    narration = narration_from_script(script)
    if len(narration) > _MAX_CHARS:      # cap length, but end on a full sentence (else the avatar
        clipped = narration[:_MAX_CHARS]  # speaks a cut-off final word/sentence)
        cut = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
        narration = (clipped[:cut + 1] if cut > _MAX_CHARS * 0.6 else clipped.rsplit(" ", 1)[0]).strip()
    if not narration:
        return {"ok": False, "error": "no narration text found in the script"}
    avatar = avatar_id or os.getenv("HEYGEN_AVATAR_ID") or _DEFAULT_AVATAR
    voice = voice_id or os.getenv("HEYGEN_VOICE_ID") or _DEFAULT_VOICE
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


# ---------------------------------------------------------------------------
# v3 Video Agent (PRODUCED video) -- structured prompt per HeyGen's official guide
# ---------------------------------------------------------------------------
_STAT_RE = re.compile(r"(\$[\d,]+(?:\.\d+)?[KMB%+]?|\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?%|\b\d{2,}(?:,\d{3})+\b)")


def _critical_onscreen_text(narration: str, business_name: str, geo: str) -> list[str]:
    """Every literal string Video Agent must render EXACTLY (else it summarizes/rounds numbers): the
    business name + city, and each hard statistic/dollar figure/percentage in the narration."""
    out: list[str] = []
    if business_name:
        out.append(business_name + (f" — {geo.split(',')[0].strip()}" if geo else ""))
    seen = set()
    for m in _STAT_RE.findall(narration or ""):
        s = m.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:8]


def build_video_agent_prompt(narration: str, *, business_name: str, geo: str, title: str = "",
                             seconds: int = 90) -> str:
    """Assemble a HeyGen Video Agent prompt per the official guide: FORMAT/TONE + AVATAR framing +
    the message + a CRITICAL ON-SCREEN TEXT block + a COMPLIANCE-CONSTRAINED faithfulness directive
    (regulated finance: the Agent may enrich VISUALS but must not invent spoken claims) + the style
    block LAST. Content first, technical directives (English) at the end."""
    city = (geo or "").split(",")[0].strip()
    onscreen = _critical_onscreen_text(narration, business_name, geo)
    parts = [
        f"FORMAT: A ~{seconds}-second professional explainer video for {business_name}"
        + (f", a financial-services team in {city}" if city else "") + ". Landscape. "
        "Confident, warm, and trustworthy tone — credible, not hypey.",
        "AVATAR: The selected presenter delivers the narration on camera; intercut with B-roll and "
        "motion-graphic overlays.",
        "",
        "MESSAGE TO CONVEY:",
        narration.strip(),
    ]
    if onscreen:
        parts += ["", "CRITICAL ON-SCREEN TEXT (display these literally, do not rephrase or round):"]
        parts += [f"- {s}" for s in onscreen]
    parts += [
        "",
        # The skill's default directive grants "full creative freedom to expand/add examples" — for
        # regulated financial content that is unsafe, so we CONSTRAIN it to visuals only.
        "FAITHFULNESS (regulated financial content — follow exactly): Convey the message above "
        "faithfully. You MAY enrich the VISUALS (B-roll, motion graphics, chapter cards) and improve "
        "pacing, but do NOT add, remove, or alter any financial claim, statistic, figure, product "
        "detail, or statement in the spoken narration — the narration must convey exactly this vetted "
        "message. Do NOT invent new financial facts, figures, testimonials, or advice. No guaranteed "
        "returns, no performance promises, no '#1'/'best'. Front-load the hook in the first 5 seconds. "
        "Do not pad with silence.",
        "",
        f"STYLE: {_STYLE_CATCHALL}",
    ]
    return "\n".join(parts)


def callback_base() -> str:
    """Public base URL for the HeyGen completion webhook (Railway sets RAILWAY_PUBLIC_DOMAIN on the
    API service). Overridable via HEYGEN_CALLBACK_BASE. '' -> no webhook (the hourly sweep still runs)."""
    base = os.getenv("HEYGEN_CALLBACK_BASE", "").strip().rstrip("/")
    if base:
        return base
    dom = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    return f"https://{dom}" if dom else ""


def start_agent_session(business_id: int, script: str, *, title: str = "", business_name: str = "",
                        geo: str = "", avatar_id: Optional[str] = None, voice_id: Optional[str] = None,
                        orientation: str = "landscape", callback_url: Optional[str] = None,
                        callback_id: Optional[str] = None) -> dict:
    """Create a v3 Video Agent session (POST /v3/video-agents) and return IMMEDIATELY (no poll), so a
    ~20-45 min render never blocks the worker. Returns {ok, session_id, video_id, prompt} or
    {skipped}/{ok:False}. The caller stores session_id; a webhook (or the poll sweep) finishes it."""
    if not configured():
        return {"skipped": True, "reason": "HeyGen not configured (set HEYGEN_API_KEY)"}
    narration = narration_from_script(script)[:_MAX_CHARS]
    if not narration:
        return {"ok": False, "error": "no narration text found in the script"}
    prompt = build_video_agent_prompt(narration, business_name=business_name or title, geo=geo, title=title)
    hdr = {"X-Api-Key": _key(), "Content-Type": "application/json"}
    body = {"prompt": prompt, "avatar_id": (avatar_id or os.getenv("HEYGEN_AVATAR_ID") or _DEFAULT_AVATAR),
            "voice_id": (voice_id or os.getenv("HEYGEN_VOICE_ID") or _DEFAULT_VOICE),
            "orientation": orientation, "mode": "generate"}
    sid_style = os.getenv("HEYGEN_STYLE_ID")
    if sid_style:
        body["style_id"] = sid_style
    if callback_url:      # webhook -> low-latency completion (the poll sweep is the fallback)
        body["callback_url"] = callback_url
        if callback_id:
            body["callback_id"] = callback_id
    start = _http.request_json("POST", _AGENT_CREATE, headers=hdr, json=body, timeout=60,
                               max_retries=2, guard_redirects=True)
    if start.failed or not isinstance(start.data, dict):
        return {"ok": False, "error": start.error or "Video Agent create failed"}
    data = start.data.get("data") if isinstance(start.data.get("data"), dict) else start.data
    session_id = data.get("session_id")
    if not session_id:
        return {"ok": False, "error": f"no session_id from Video Agent: {str(start.data)[:200]}"}
    return {"ok": True, "session_id": session_id, "video_id": data.get("video_id"), "prompt": prompt}


def fetch_agent_video(business_id: int, session_id: str, *, video_id: Optional[str] = None,
                      prompt: str = "", work_order_id: Optional[int] = None,
                      draft_id: Optional[int] = None) -> dict:
    """Check a Video Agent session ONCE (a couple HTTP calls, never a long block). If completed, fetch
    + download the MP4/SRT and store a `video` visual_asset -> {ok, visual_id, ...}. If still
    rendering -> {pending: True, status, progress}. If failed -> {ok: False, failed: True, error}."""
    if not configured():
        return {"skipped": True, "reason": "HeyGen not configured"}
    hdr = {"X-Api-Key": _key(), "Content-Type": "application/json"}
    st = _http.request_json("GET", f"{_AGENT_CREATE}/{session_id}", headers=hdr, timeout=30,
                            max_retries=2, guard_redirects=True)
    if st.failed or not isinstance(st.data, dict):
        return {"pending": True, "status": "unknown"}
    d = st.data.get("data") or {}
    status = (d.get("status") or "").lower()
    video_id = d.get("video_id") or video_id
    if status in ("failed", "error"):
        return {"ok": False, "failed": True,
                "error": f"Video Agent failed: {d.get('failure_message') or str(d)[:200]}"}
    if status not in ("completed", "success", "done") or not video_id:
        return {"pending": True, "status": status or "generating", "progress": d.get("progress")}
    vg = _http.request_json("GET", f"{_VIDEO_GET}/{video_id}", headers=hdr, timeout=30,
                            max_retries=2, guard_redirects=True)
    vd = (vg.data.get("data") if isinstance(vg.data, dict) else {}) or {}
    video_url = vd.get("video_url") or vd.get("captioned_video_url")
    srt_url = vd.get("subtitle_url")
    duration = vd.get("duration")
    if not video_url:
        return {"pending": True, "status": "completed_no_url"}
    raw = _download_binary(video_url)
    if not raw:
        return {"ok": False, "error": "could not download the Video Agent MP4"}
    srt = ""
    if srt_url:
        sb = _download_binary(srt_url, timeout=60)
        srt = sb.decode("utf-8", "replace") if sb else ""
    try:
        from . import visual_content as _vc
    except ImportError:  # pragma: no cover
        import visual_content as _vc  # type: ignore
    path = _vc._save_png(business_id, raw, ext="mp4")
    visual_id = _vc._persist(
        business_id, kind="video", provider="heygen_agent", model="video_agent_v3",
        prompt=(prompt or "")[:500], file_path=path, url=video_url,
        compliance_note="Produced by HeyGen Video Agent (non-verbatim; visuals-constrained prompt) — review narration before publish.",
        work_order_id=work_order_id, draft_id=draft_id, file_bytes=raw, mime="video/mp4",
        meta={"source": "heygen_agent", "srt": srt, "duration": duration, "session_id": session_id})
    try:
        from . import cost as _cost
        _cost.record_cost(business_id, None, "video", "heygen", "render_agent",
                          units=float(duration or 0) or 90.0, unit_label="seconds",
                          model="video_agent_v3", detail={"content_type": "video", "api": "heygen_video_agent"})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "visual_id": visual_id, "video_url": video_url, "srt": srt,
            "duration": duration, "file_path": path, "session_id": session_id}


def render_agent(business_id: int, script: str, *, title: str = "", business_name: str = "",
                 geo: str = "", work_order_id: Optional[int] = None, draft_id: Optional[int] = None,
                 avatar_id: Optional[str] = None, voice_id: Optional[str] = None,
                 orientation: str = "landscape") -> dict:
    """BLOCKING convenience: start a Video Agent session and poll to completion (~20-45 min). In
    production prefer async (start_agent_session + a poll_pending sweep) so the worker isn't blocked;
    this stays for direct/CLI/test use. Produced video is NON-VERBATIM (visuals-constrained + human-
    reviewed before publish)."""
    started = start_agent_session(business_id, script, title=title, business_name=business_name,
                                  geo=geo, avatar_id=avatar_id, voice_id=voice_id, orientation=orientation)
    if not started.get("ok"):
        return started
    sid, vid, prompt = started["session_id"], started.get("video_id"), started.get("prompt", "")
    for _ in range(_AGENT_MAX_POLLS):
        time.sleep(_AGENT_POLL_SECONDS)
        res = fetch_agent_video(business_id, sid, video_id=vid, prompt=prompt,
                                work_order_id=work_order_id, draft_id=draft_id)
        if not res.get("pending"):
            return res
    return {"ok": False, "error": "Video Agent timed out"}
