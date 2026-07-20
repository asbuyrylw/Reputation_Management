"""Katteb content-scoring API (selective quality layer over our own generator).

- GET  /katteb/credits                     -> remaining monthly credits (for the UI to show budget)
- POST /drafts/{id}/analyze-seo            -> enqueue a HEAVY (1000-credit) SEO/competitor analysis;
                                              the worker stores the result in quality_notes.katteb
- POST /drafts/{id}/humanize               -> synchronous humanizer rewrite (100 credits), returns
                                              the rewritten text for the operator to accept or ignore
- POST /drafts/{id}/factcheck              -> synchronous claim verification (100 credits)

All human-triggered + editor-gated; dormant-safe (skipped without KATTEB_API_KEY). See rep_engine.katteb.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, get_current_user, require_business_editor

try:
    from ... import katteb as _kb
except ImportError:  # pragma: no cover
    import katteb as _kb  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["katteb"])


@router.get("/katteb/credits")
def katteb_credits(business_id: int = Depends(authorize_business)):
    """Remaining Katteb credits + configured flag, so the UI can show the budget and gate actions."""
    if not _kb.configured():
        return {"configured": False}
    c = _kb.credits()
    return {"configured": True, "ok": c.get("ok", False),
            "credits_available": c.get("credits_available"), "credits_total": c.get("credits_total"),
            "plan_tier": c.get("plan_tier")}


def _own_draft(conn, draft_id: int, business_id: int) -> dict:
    row = conn.execute(
        "SELECT id, body, target_query FROM content_drafts WHERE id=%s AND business_id=%s",
        (draft_id, business_id)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return dict(row)


@router.post("/drafts/{draft_id}/analyze-seo")
def analyze_seo(draft_id: int, business_id: int = Depends(require_business_editor),
                user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    """Kick off a Katteb SEO + competitor analysis for this draft (≈1000 credits). Runs as a job
    (1-3 min); when done, quality_notes.katteb carries the score, benchmark, and competitor table."""
    if not _kb.configured():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Katteb isn't configured (set KATTEB_API_KEY).")
    _own_draft(conn, draft_id, business_id)
    try:
        from .. import jobs as _jobs
        job_id, active = _jobs.enqueue(business_id, "katteb_seo", requested_by=user["id"],
                                       args={"draft_id": draft_id})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"could not queue: {e}")
    return {"ok": True, "job_id": job_id or active, "queued": bool(job_id)}


@router.post("/drafts/{draft_id}/humanize")
def humanize(draft_id: int, business_id: int = Depends(require_business_editor),
             conn=Depends(get_conn)):
    """Rewrite the draft to read more human (≈100 credits). Returns the rewritten text; the operator
    decides whether to save it over the draft (we don't overwrite automatically)."""
    if not _kb.configured():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Katteb isn't configured.")
    d = _own_draft(conn, draft_id, business_id)
    res = _kb.humanize_rewrite(d["body"] or "")
    if res.get("skipped") or not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("error", "humanize failed"))
    return {"ok": True, "rewritten_text": res.get("rewritten_text"),
            "credits_charged": res.get("credits_charged")}


class ClaimBody(BaseModel):
    claim: str


@router.post("/drafts/{draft_id}/factcheck")
def factcheck(draft_id: int, body: ClaimBody, business_id: int = Depends(require_business_editor),
              conn=Depends(get_conn)):
    """Verify one factual claim from the draft (≈100 credits). Returns verdict + references."""
    if not _kb.configured():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Katteb isn't configured.")
    _own_draft(conn, draft_id, business_id)
    claim = (body.claim or "").strip()
    if not claim:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "claim required")
    res = _kb.factcheck(claim)
    if res.get("skipped") or not res.get("ok"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, res.get("error", "fact-check failed"))
    return {"ok": True, "verdict": res.get("verdict"), "is_fact": res.get("is_fact"),
            "explanation": res.get("explanation"), "references": res.get("references") or [],
            "credits_charged": res.get("credits_charged")}
