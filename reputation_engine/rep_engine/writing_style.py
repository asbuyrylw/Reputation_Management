"""
Reputation Crowding-Out Engine -- brand writing-style cloning (from a URL)
==========================================================================
Analyze the writing STYLE of an existing article (how it's written, not what it's about) into a
reusable profile, and let the operator set an ACTIVE style. `active_profile(business_id)` is read
by content_generator so every generated piece matches the brand's voice. Applies to ALL our own
content -- our generator is the primary engine, so the brand's own voice grounds every draft.

Dormant-safe: analysis needs the orchestrator LLM (returns {skipped} without it) and a fetchable
URL; storing/activating styles is pure DB and always works.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

try:
    from .db import db
    from . import http as _http
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import http as _http  # type: ignore

log = logging.getLogger("writing_style")

_STYLE_SYSTEM = (
    "You are a writing-style analyst. Given an article's text, describe HOW it is written so another "
    "writer can match the voice -- NOT what it is about. Output STRICT JSON: {\"tone\": str, "
    "\"sentence_length\": str, \"vocabulary\": str, \"point_of_view\": str, \"formatting_quirks\": "
    "str, \"summary\": str}. `summary` is a 2-3 sentence style guide a writer could follow. Be "
    "concrete (e.g. 'short punchy sentences, second person, contractions, occasional rhetorical "
    "questions, no jargon')."
)


def _strip_html(html: str) -> str:
    """Crude HTML -> visible text (drop script/style, tags, collapse whitespace)."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_text(url: str) -> str:
    """SSRF-guarded fetch of a URL's visible text (best-effort)."""
    res = _http.request_json("GET", url, parse_json=False, timeout=25, max_retries=2, guard_redirects=True)
    if res.failed or not res.text:
        return ""
    return _strip_html(res.text)[:6000]


def analyze_url(business_id: int, url: str, *, name: Optional[str] = None) -> dict:
    """Fetch the URL, extract a style profile via the LLM, and store it (inactive). Returns the row
    or {ok:False,error}. Human-triggered."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "Enter a full article URL (https://…)."}
    text = _fetch_text(url)
    if len(text) < 200:
        return {"ok": False, "error": "Couldn't read enough article text from that URL."}
    try:
        from . import ai_state_audit as llm
    except ImportError:  # pragma: no cover
        import ai_state_audit as llm  # type: ignore
    import json as _json
    res = llm.orchestrator_json(_STYLE_SYSTEM, _json.dumps({"article_text": text}), tier="cheap",
                                bill={"business_id": business_id, "operation": "writing_style"})
    if not res or not isinstance(res, dict):
        return {"ok": False, "error": "Style analysis unavailable (LLM). Try again."}
    profile = _format_profile(res)
    nm = (name or "").strip() or _domain(url)
    with db() as conn:
        row = conn.execute(
            "INSERT INTO writing_styles (business_id, name, source_url, profile) "
            "VALUES (%s,%s,%s,%s) RETURNING id, name, source_url, active, created_at",
            (business_id, nm, url, profile)).fetchone()
        conn.commit()
    return {"ok": True, "id": row["id"], "name": row["name"], "source_url": row["source_url"],
            "active": row["active"], "profile": profile}


def _domain(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return (m.group(1) if m else url)[:60]


def _format_profile(d: dict) -> str:
    parts = []
    for k in ("tone", "sentence_length", "vocabulary", "point_of_view", "formatting_quirks"):
        v = (d.get(k) or "").strip()
        if v:
            parts.append(f"{k.replace('_', ' ').title()}: {v}")
    if d.get("summary"):
        parts.append(f"Style guide: {d['summary'].strip()}")
    return " | ".join(parts)[:1500]


def list_styles(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, name, source_url, profile, active, created_at FROM writing_styles "
            "WHERE business_id=%s ORDER BY active DESC, id DESC", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def set_active(business_id: int, style_id: Optional[int]) -> bool:
    """Make one style active (or clear all if style_id is None)."""
    with db() as conn:
        conn.execute("UPDATE writing_styles SET active=FALSE WHERE business_id=%s AND active", (business_id,))
        if style_id is not None:
            r = conn.execute("UPDATE writing_styles SET active=TRUE WHERE id=%s AND business_id=%s RETURNING id",
                             (style_id, business_id)).fetchone()
            conn.commit()
            return bool(r)
        conn.commit()
    return True


def delete_style(business_id: int, style_id: int) -> bool:
    with db() as conn:
        r = conn.execute("DELETE FROM writing_styles WHERE id=%s AND business_id=%s RETURNING id",
                         (style_id, business_id)).fetchone()
        conn.commit()
    return bool(r)


def active_profile(business_id: int) -> str:
    """The active style's profile string (or '' if none). Read by content_generator to shape voice."""
    try:
        with db() as conn:
            r = conn.execute("SELECT profile FROM writing_styles WHERE business_id=%s AND active LIMIT 1",
                             (business_id,)).fetchone()
        return (r or {}).get("profile") or "" if r else ""
    except Exception:  # noqa: BLE001 -- best-effort; never block generation
        return ""
