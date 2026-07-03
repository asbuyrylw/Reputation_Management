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
    """Resolve report branding: per-business branding overrides, else env, else the default brand."""
    name = logo = accent = None
    try:
        with db() as conn:
            r = conn.execute("SELECT branding FROM businesses WHERE id=%s", (business_id,)).fetchone()
        br = (r or {}).get("branding") or {}
        if isinstance(br, dict):
            name, logo, accent = br.get("brand_name"), br.get("logo_url"), br.get("accent")
    except Exception:  # noqa: BLE001 -- column may not exist on an un-migrated DB
        pass
    return {"brand_name": name or os.getenv("REPORT_BRAND_NAME") or "Reputation Console",
            "logo_url": logo or os.getenv("REPORT_BRAND_LOGO") or None,
            "accent": accent or os.getenv("REPORT_BRAND_ACCENT") or None}


def set_branding(business_id: int, *, brand_name: Optional[str] = None, logo_url: Optional[str] = None,
                 accent: Optional[str] = None) -> dict:
    """Set the per-business white-label branding (merges into businesses.branding)."""
    from psycopg.types.json import Json
    fields = {k: v for k, v in (("brand_name", brand_name), ("logo_url", logo_url), ("accent", accent))
              if v is not None}
    with db() as conn:
        conn.execute("UPDATE businesses SET branding = COALESCE(branding,'{}'::jsonb) || %s::jsonb WHERE id=%s",
                     (Json(fields), business_id))
        conn.commit()
    return branding(business_id)


# ---------------------------------------------------------------------------
# Public lead-magnet funnel (item 20)
# ---------------------------------------------------------------------------
def _origin() -> str:
    return (os.getenv("PUBLIC_APP_ORIGIN") or "http://localhost:3000").rstrip("/")


def ensure_share_token(business_id: int) -> dict:
    """Get-or-create the unguessable public token + return the public audit URL."""
    import secrets
    with db() as conn:
        r = conn.execute("SELECT public_token FROM businesses WHERE id=%s", (business_id,)).fetchone()
        token = (r or {}).get("public_token")
        if not token:
            token = secrets.token_urlsafe(12)
            conn.execute("UPDATE businesses SET public_token=%s WHERE id=%s", (token, business_id))
            conn.commit()
    return {"token": token, "url": f"{_origin()}/audit/{token}"}


def resolve_token(token: str) -> Optional[int]:
    if not token:
        return None
    with db() as conn:
        r = conn.execute("SELECT id FROM businesses WHERE public_token=%s", (token,)).fetchone()
    return r["id"] if r else None


def summary_for_token(token: str) -> dict:
    """Public read: the sanitized audit teaser + branding for the share page. None -> not found."""
    bid = resolve_token(token)
    if not bid:
        return {"found": False}
    out = public_summary(bid)
    out["branding"] = branding(bid)
    return out


def capture_lead(token: str, email: str, name: Optional[str] = None) -> dict:
    """Capture an email from the public page (idempotent per business+email)."""
    bid = resolve_token(token)
    if not bid:
        return {"ok": False, "reason": "invalid link"}
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "reason": "invalid email"}
    with db() as conn:
        conn.execute(
            "INSERT INTO leads (business_id, email, name, source) VALUES (%s,%s,%s,'public_audit') "
            "ON CONFLICT (business_id, email) DO NOTHING", (bid, email, name))
        conn.commit()
    return {"ok": True}


def list_leads(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, email, name, source, captured_at FROM leads WHERE business_id=%s "
            "ORDER BY captured_at DESC LIMIT 500", (business_id,)).fetchall()
    return [dict(r) for r in rows]
