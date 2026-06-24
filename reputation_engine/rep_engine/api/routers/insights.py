"""SEO site audit + gap model (Phase 2 reads). Both return the latest persisted
JSONB document (or null when none exists yet)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, require_business_editor

router = APIRouter(prefix="/businesses/{business_id}", tags=["insights"])


class CompetitorCreate(BaseModel):
    name: str
    domain: Optional[str] = ""


@router.get("/site-audit")
def site_audit(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT summary, created_at FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/gap-model")
def gap_model(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    row = conn.execute(
        "SELECT model, created_at FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
        (business_id,),
    ).fetchone()
    return dict(row) if row else None


@router.get("/social-presence")
def social_presence(business_id: int = Depends(authorize_business)):
    """Latest best-effort verification of which social profiles the business actually has,
    so the social recommendations can show confirmed 'create' vs 'improve'."""
    from ... import social_presence as _sp
    return _sp.latest(business_id)


# ---- competitor benchmarking (share-of-voice vs rivals) ----
@router.get("/competitors")
def competitors(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, name, domain, created_at FROM competitors WHERE business_id=%s ORDER BY id",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/competitors/compare")
def competitors_compare(business_id: int = Depends(authorize_business)):
    """Latest benchmark: how often AI surfaces YOU vs each competitor for category questions."""
    from ... import competitor as _c
    return _c.compare(business_id, quiet=True)


@router.get("/visibility-trend")
def visibility_trend(business_id: int = Depends(authorize_business)):
    """Subject vs competitor appearance rate over time (one point per benchmark run) --
    backs the visibility-over-time chart with competitor lines."""
    from ... import competitor as _c
    return _c.trend(business_id)


@router.get("/onboarding")
def onboarding(business_id: int = Depends(authorize_business)):
    """Getting-started checklist state for this business (derived from existing data)."""
    from ... import onboarding as _o
    return _o.status(business_id)


@router.get("/prompt-results")
def prompt_results(business_id: int = Depends(authorize_business)):
    """Per-prompt visibility/sentiment/goal-alignment for the latest completed audit run --
    how each tracked question performs, with a per-engine split. Null prompts list when no
    completed run exists yet."""
    from ...ai_state_audit import per_prompt_metrics
    return per_prompt_metrics(business_id)


@router.get("/local-rankings")
def local_rankings(business_id: int = Depends(authorize_business)):
    """Latest local Google rank snapshot (organic + map pack) for the category-local
    queries -- our rank vs competitors, plus page-1 / local-pack roll-ups. Null when no
    run has been captured yet (needs SERPER_API_KEY)."""
    from ... import local_seo as _ls
    return _ls.latest(business_id)


@router.post("/competitors", status_code=201)
def add_competitor(payload: CompetitorCreate, business_id: int = Depends(require_business_editor)):
    from ... import competitor as _c
    name = payload.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "name required")
    cid = _c.register_competitor(business_id, name, (payload.domain or "").strip())
    return {"id": cid, "name": name}


@router.delete("/competitors/{competitor_id}")
def delete_competitor(competitor_id: int, business_id: int = Depends(require_business_editor),
                      conn=Depends(get_conn)):
    r = conn.execute("DELETE FROM competitors WHERE id=%s AND business_id=%s RETURNING id",
                     (competitor_id, business_id)).fetchone()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competitor not found")
    conn.commit()
    return {"deleted": competitor_id}
