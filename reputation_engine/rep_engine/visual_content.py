"""
Reputation Crowding-Out Engine -- visual content generation (LATER: CI-4)
=========================================================================
Generates compliance-safe visuals to accompany owned content: AI images, locally-rendered
quote-cards, and (LLM-scripted) short-video briefs. Everything is HUMAN-GATED -- a visual is
'generated' until a reviewer approves it; nothing auto-publishes.

DORMANT BY DEFAULT. The image/video PROVIDER + MODEL are chosen via env so the operator only has
to drop in an API key (the design promise: "all I need to do is add the API Key"):

    IMAGE_PROVIDER=openai            # openai | stability | replicate
    IMAGE_MODEL=gpt-image-1
    IMAGE_API_KEY=                   # falls back to OPENAI_API_KEY when provider=openai
    VIDEO_PROVIDER=                  # (scaffold) runway | pika | replicate -- video brief only until set
    VIDEO_MODEL=
    VIDEO_API_KEY=

Quote-cards render locally (Pillow) and need NO key. Compliance guard: for a regulated firm
(regulatory_profile.firm_type financial), AI imagery must NOT depict real/identifiable people
(likeness/endorsement risk) -- enforced in the prompt policy + flagged on the row.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from typing import Optional

try:
    from .db import db
    from . import http as _http
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import http as _http  # type: ignore

from psycopg.types.json import Json

log = logging.getLogger("visual_content")

_OUTPUT_DIR = os.getenv("REP_OUTPUT_DIR", "output")
_FINANCIAL_FIRMS = {"ria", "broker_dealer", "insurance"}

# Provider API endpoints (host-pinned; all I/O via http.request_json).
_OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"
_STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"
_GEMINI_BASE = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _image_provider() -> str:
    return (os.getenv("IMAGE_PROVIDER") or "openai").strip().lower()


def _image_model() -> str:
    m = (os.getenv("IMAGE_MODEL") or "").strip()
    if m:
        return m
    # Gemini default = Imagen 4 (high-quality dedicated image model); OpenAI default = gpt-image-1.
    return "imagen-4.0-generate-001" if _image_provider() == "gemini" else "gpt-image-1"


def _image_key() -> str:
    prov = _image_provider()
    explicit = os.getenv("IMAGE_API_KEY", "").strip()
    if explicit:
        return explicit
    if prov == "openai":
        return os.getenv("OPENAI_API_KEY", "").strip()
    if prov == "stability":
        return os.getenv("STABILITY_API_KEY", "").strip()
    if prov == "replicate":
        return os.getenv("REPLICATE_API_TOKEN", "").strip()
    if prov == "gemini":
        return os.getenv("GEMINI_API_KEY", "").strip()
    return ""


def image_configured() -> bool:
    return bool(_image_key())


def video_configured() -> bool:
    return bool((os.getenv("VIDEO_PROVIDER") or "").strip() and (os.getenv("VIDEO_API_KEY") or "").strip())


# ---------------------------------------------------------------------------
# Compliance policy
# ---------------------------------------------------------------------------
def _reg_firm_type(business_id: int) -> str:
    try:
        with db() as conn:
            r = conn.execute("SELECT regulatory_profile FROM businesses WHERE id=%s", (business_id,)).fetchone()
        rp = (r or {}).get("regulatory_profile") or {}
        return (rp.get("firm_type") or "").lower() if isinstance(rp, dict) else ""
    except Exception:  # noqa: BLE001
        return ""


def _image_policy(business_id: int) -> tuple[str, Optional[str]]:
    """Return (prompt-policy-suffix, compliance_note). Regulated firms forbid real-people likenesses."""
    if _reg_firm_type(business_id) in _FINANCIAL_FIRMS:
        return (" Do NOT depict real, identifiable, or named individuals or their faces; use abstract, "
                "brand, iconographic, or generic conceptual imagery only. No text claiming guarantees "
                "or performance. No logos of other companies.",
                "Regulated firm: no real-person likenesses (likeness/endorsement compliance).")
    return (" Use original, non-infringing imagery; no real-person likenesses without consent; no "
            "third-party logos.", None)


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------
def _save_png(business_id: int, raw: bytes, ext: str = "png") -> str:
    d = os.path.join(_OUTPUT_DIR, "visuals", str(business_id))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{secrets.token_hex(8)}.{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _persist(business_id: int, *, kind: str, provider: Optional[str], model: Optional[str],
             prompt: str, file_path: Optional[str], url: Optional[str], compliance_note: Optional[str],
             work_order_id=None, draft_id=None, width=None, height=None, meta=None) -> int:
    with db() as conn:
        row = conn.execute(
            "INSERT INTO visual_assets (business_id, work_order_id, draft_id, kind, provider, model, "
            "prompt, file_path, url, width, height, compliance_note, meta) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (business_id, work_order_id, draft_id, kind, provider, model, prompt, file_path, url,
             width, height, compliance_note, Json(meta or {}))).fetchone()
        conn.commit()
    return int(row["id"])


def generate_image(business_id: int, prompt: str, *, kind: str = "image", size: str = "1024x1024",
                   work_order_id: Optional[int] = None, draft_id: Optional[int] = None) -> dict:
    """Generate one AI image via the configured provider, apply the compliance policy, and persist a
    human-gated visual_assets row. Keyless-safe: returns {skipped} if no provider key is set."""
    if not image_configured():
        return {"skipped": True, "reason": "no image provider key set (IMAGE_API_KEY / OPENAI_API_KEY)"}
    policy, note = _image_policy(business_id)
    full_prompt = (prompt or "").strip() + policy
    provider, model = _image_provider(), _image_model()
    try:
        if provider == "openai":
            raw = _openai_image(full_prompt, model, size)
        elif provider == "stability":
            raw = _stability_image(full_prompt)
        elif provider == "gemini":
            raw = _gemini_image(full_prompt, model, size)
        else:
            return {"skipped": True, "reason": f"unsupported IMAGE_PROVIDER '{provider}'"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if not raw:
        return {"ok": False, "error": "provider returned no image"}
    path = _save_png(business_id, raw)
    vid = _persist(business_id, kind=kind, provider=provider, model=model, prompt=full_prompt,
                   file_path=path, url=None, compliance_note=note,
                   work_order_id=work_order_id, draft_id=draft_id)
    return {"ok": True, "visual_id": vid, "file_path": path, "provider": provider, "model": model,
            "compliance_note": note}


def _openai_image(prompt: str, model: str, size: str) -> Optional[bytes]:
    res = _http.request_json(
        "POST", _OPENAI_IMAGE_URL,
        headers={"Authorization": f"Bearer {_image_key()}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "size": size, "n": 1},
        timeout=120, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        raise RuntimeError(res.error or "openai image failed")
    data = (res.data.get("data") or [{}])[0]
    if data.get("b64_json"):
        return base64.b64decode(data["b64_json"])
    if data.get("url"):
        # Some models (e.g. DALL·E) return a URL instead of b64. Fetch the BINARY safely --
        # request_json only yields decoded text, which would corrupt a PNG, so use a guarded
        # raw download.
        return _download_bytes(data["url"])
    return None


def _download_bytes(url: str, *, timeout: int = 60) -> Optional[bytes]:
    """SSRF-guarded binary download (for image URLs). netguard validates the host before the
    fetch; binary bytes can't go through http.request_json (which decodes to text)."""
    try:
        from . import netguard as _ng
    except ImportError:  # pragma: no cover
        import netguard as _ng  # type: ignore
    try:
        _ng.assert_url_allowed(url)
    except Exception as e:  # noqa: BLE001 -- UnsafeURLError
        log.warning("image url blocked by SSRF guard: %s", e)
        return None
    import requests
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=False)
        return r.content if r.ok else None
    except Exception as e:  # noqa: BLE001
        log.warning("image download failed: %s", e)
        return None


def _stability_image(prompt: str) -> Optional[bytes]:
    res = _http.request_json(
        "POST", _STABILITY_URL,
        headers={"Authorization": f"Bearer {_image_key()}", "Accept": "application/json"},
        data={"prompt": prompt, "output_format": "png"},
        timeout=120, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        raise RuntimeError(res.error or "stability image failed")
    b64 = res.data.get("image")
    return base64.b64decode(b64) if b64 else None


def _aspect_from_size(size: str) -> str:
    """Nearest Imagen aspect ratio for a WxH size (Imagen supports 1:1, 3:4, 4:3, 9:16, 16:9)."""
    try:
        w, h = (int(x) for x in (size or "1024x1024").lower().split("x"))
        r = w / h
    except Exception:  # noqa: BLE001
        return "1:1"
    if r >= 1.5:
        return "16:9"
    if r >= 1.15:
        return "4:3"
    if r <= 0.6:
        return "9:16"
    if r <= 0.85:
        return "3:4"
    return "1:1"


def _gemini_image(prompt: str, model: str, size: str) -> Optional[bytes]:
    """Google image generation via the GEMINI API key. Handles both Imagen models
    (…:predict -> predictions[].bytesBase64Encoded) and gemini-*-image models
    (…:generateContent -> candidates[].content.parts[].inlineData)."""
    key = _image_key()
    if not key:
        raise RuntimeError("no Gemini API key")
    hdr = {"Content-Type": "application/json", "x-goog-api-key": key}
    if model.startswith("imagen"):
        res = _http.request_json(
            "POST", f"{_GEMINI_BASE}/models/{model}:predict", headers=hdr,
            json={"instances": [{"prompt": prompt}],
                  "parameters": {"sampleCount": 1, "aspectRatio": _aspect_from_size(size)}},
            timeout=180, max_retries=2, guard_redirects=True)
        if res.failed or not isinstance(res.data, dict):
            raise RuntimeError(res.error or "imagen image failed")
        preds = res.data.get("predictions") or []
        b64 = (preds[0] or {}).get("bytesBase64Encoded") if preds else None
        return base64.b64decode(b64) if b64 else None
    # gemini-*-image via generateContent (inline image bytes)
    res = _http.request_json(
        "POST", f"{_GEMINI_BASE}/models/{model}:generateContent", headers=hdr,
        json={"contents": [{"parts": [{"text": f"{prompt} Target size ~{size}."}]}]},
        timeout=180, max_retries=2, guard_redirects=True)
    if res.failed or not isinstance(res.data, dict):
        raise RuntimeError(res.error or "gemini image failed")
    parts = (((res.data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    for p in parts:
        inl = p.get("inlineData") or p.get("inline_data")
        if inl and inl.get("data"):
            return base64.b64decode(inl["data"])
    return None


# ---------------------------------------------------------------------------
# Quote-card (local render -- no API key)
# ---------------------------------------------------------------------------
def generate_quote_card(business_id: int, text: str, *, attribution: Optional[str] = None,
                        work_order_id: Optional[int] = None) -> dict:
    """Render a branded quote-card locally with Pillow (no API key). Always available."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # noqa: BLE001 -- Pillow missing
        return {"skipped": True, "reason": "Pillow not installed (pip install pillow)"}
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), (15, 23, 42))  # slate-900
    draw = ImageDraw.Draw(img)
    # subtle vertical brand gradient
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=(int(15 + 24 * t), int(23 + 14 * t), int(42 + 40 * t)))
    def _font(sz: int):
        for name in ("arial.ttf", "DejaVuSans.ttf", "Helvetica.ttf"):
            try:
                return ImageFont.truetype(name, sz)
            except Exception:  # noqa: BLE001
                continue
        return ImageFont.load_default()
    font, small, big = _font(54), _font(32), _font(120)
    # word-wrap
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) > W - 160:
            lines.append(cur); cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    y = H // 2 - (len(lines) * 64) // 2
    draw.text((80, y - 80), "“", font=big, fill=(99, 102, 241))
    for ln in lines:
        draw.text((80, y), ln, font=font, fill=(241, 245, 249)); y += 70
    if attribution:
        draw.text((80, y + 30), f"— {attribution}", font=small, fill=(148, 163, 184))
    raw_path = _save_png_image(business_id, img)
    vid = _persist(business_id, kind="quote_card", provider="local", model="pillow",
                   prompt=text, file_path=raw_path, url=None, compliance_note=None,
                   work_order_id=work_order_id, width=W, height=H)
    return {"ok": True, "visual_id": vid, "file_path": raw_path}


def _save_png_image(business_id: int, img) -> str:
    d = os.path.join(_OUTPUT_DIR, "visuals", str(business_id))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{secrets.token_hex(8)}.png")
    img.save(path, "PNG")
    return path


# ---------------------------------------------------------------------------
# Video brief (LLM script; generative video deferred behind VIDEO_* env)
# ---------------------------------------------------------------------------
_VIDEO_BRIEF_SYSTEM = (
    "You write a SHORT-FORM video brief for a business's owned social channels. Output STRICT JSON: "
    "{\"hook\": str, \"script\": [str], \"shotlist\": [str], \"caption\": str, \"hashtags\": [str], "
    "\"cta\": str}. 20-40 seconds, on-brand, factual, no guarantees/performance claims for financial "
    "firms, no real-person likeness requirements."
)


def generate_video_brief(business_id: int, topic: str, *, work_order_id: Optional[int] = None) -> dict:
    """Produce a human-shootable short-video brief (script + shotlist). Generative video itself is
    deferred until VIDEO_PROVIDER/VIDEO_API_KEY are set; the brief is always produced."""
    try:
        from . import content_generator as cg
    except ImportError:  # pragma: no cover
        import content_generator as cg  # type: ignore
    brief = cg.llm.orchestrator_json(_VIDEO_BRIEF_SYSTEM,
                                     json.dumps({"topic": topic, "business_id": business_id}), tier="mid")
    if not brief:
        return {"skipped": True, "reason": "LLM unavailable for video brief"}
    vid = _persist(business_id, kind="video_brief", provider="llm", model="orchestrator",
                   prompt=topic, file_path=None, url=None,
                   compliance_note=("generative video deferred (set VIDEO_PROVIDER/VIDEO_API_KEY to enable)"
                                    if not video_configured() else None),
                   work_order_id=work_order_id, meta={"brief": brief})
    return {"ok": True, "visual_id": vid, "brief": brief, "generative_video": video_configured()}


# ---------------------------------------------------------------------------
# Queue management
# ---------------------------------------------------------------------------
def list_visuals(business_id: int, status: Optional[str] = None) -> list[dict]:
    where = "business_id=%s" + (" AND status=%s" if status else "")
    params = (business_id, status) if status else (business_id,)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, work_order_id, draft_id, kind, provider, model, prompt, file_path, url, "
            "width, height, status, compliance_note, reviewer, reviewed_at, meta, created_at "
            f"FROM visual_assets WHERE {where} ORDER BY id DESC", params).fetchall()
    return [dict(r) for r in rows]


def set_visual_status(visual_id: int, status: str, reviewer: str, business_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "UPDATE visual_assets SET status=%s, reviewer=%s, reviewed_at=now() "
            "WHERE id=%s AND business_id=%s RETURNING id", (status, reviewer, visual_id, business_id)).fetchone()
        conn.commit()
    return bool(row)
