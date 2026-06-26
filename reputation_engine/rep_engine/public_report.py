"""
Reputation Crowding-Out Engine -- public AI-audit summary + report branding (Wave 5, items 20 + 21)
===================================================================================================
* public_summary (item 20, lead magnet): a SANITIZED single-audit summary (score + band + a few
  top gaps) safe to show on a gated public page in exchange for an email. No internal data, no PII.
  The public landing page + email-capture form is a marketing-site surface; this is its data layer.
* branding (item 21, white-label): the brand name / logo / accent applied to the client report.
  Resolves from per-business meta -> env (REPORT_BRAND_*), so an agency can white-label deliverables.
  The full per-org theming UI + subdomain is a follow-up; this is the report-side hook.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore


def _score_band(ga: Optional[float]) -> tuple[Optional[int], str]:
    if ga is None:
        return None, "Not yet measured"
    score = round((ga + 1) / 2 * 100)
    band = ("Poor" if score < 30 else "Weak" if score < 45 else "Neutral"
            if score < 60 else "Strong" if score < 80 else "Excellent")
    return score, band


def public_summary(business_id: int) -> dict:
    """Sanitized teaser of the latest audit: score, band, a couple of top gaps. Lead-magnet safe."""
    with db() as conn:
        b = conn.execute("SELECT name, geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not b:
            return {"found": False}
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL AND status='complete' "
            "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        ga = None
        if run:
            r = conn.execute("SELECT AVG(goal_alignment) g FROM answers WHERE run_id=%s AND "
                            "goal_alignment IS NOT NULL", (run["id"],)).fetchone()
            ga = r["g"] if r else None
        gap = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                          (business_id,)).fetchone()
    score, band = _score_band(float(ga) if ga is not None else None)
    top_gaps = []
    if gap:
        m = gap["model"] if isinstance(gap["model"], dict) else __import__("json").loads(gap["model"])
        for w in (m.get("weak_queries") or [])[:3]:
            top_gaps.append(w.get("prompt"))
    return {"found": True, "business": b["name"], "area": b.get("geo"),
            "score": score, "band": band,
            "top_gaps": [g for g in top_gaps if g],
            "teaser": ("See exactly what ChatGPT, Claude, Perplexity and Gemini say about "
                       f"{b['name']} — and the plan to fix it."),
            "has_audit": bool(run)}


def branding(business_id: int) -> dict:
    """Resolve report branding: per-business meta overrides, else env, else the default product brand."""
    name = logo = accent = None
    try:
        with db() as conn:
            r = conn.execute("SELECT meta FROM businesses WHERE id=%s", (business_id,)).fetchone()
        meta = (r or {}).get("meta") or {}
        if isinstance(meta, dict):
            br = meta.get("branding") or {}
            name, logo, accent = br.get("brand_name"), br.get("logo_url"), br.get("accent")
    except Exception:  # noqa: BLE001
        pass
    return {"brand_name": name or os.getenv("REPORT_BRAND_NAME") or "Reputation Console",
            "logo_url": logo or os.getenv("REPORT_BRAND_LOGO") or None,
            "accent": accent or os.getenv("REPORT_BRAND_ACCENT") or None}
