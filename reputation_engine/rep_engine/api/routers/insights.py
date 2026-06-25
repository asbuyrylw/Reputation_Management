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


@router.get("/report-view")
def report_view(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """A viewable, in-console report bundle (score, biggest gaps, Local Reputation, this-month
    work) — so the client can read the report in the browser, not just download a docx."""
    b = conn.execute("SELECT name, goal FROM businesses WHERE id=%s", (business_id,)).fetchone()
    rm = conn.execute("SELECT goal_alignment FROM run_metrics WHERE business_id=%s "
                      "ORDER BY run_id DESC LIMIT 1", (business_id,)).fetchone()
    score = round((float(rm["goal_alignment"]) + 1) / 2 * 100) if rm and rm["goal_alignment"] is not None else None
    gm = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                      (business_id,)).fetchone()
    gaps = []
    if gm and isinstance(gm["model"], dict):
        gaps = [w.get("prompt") for w in (gm["model"].get("weak_queries") or [])[:5]
                if isinstance(w, dict) and w.get("prompt")]
    tasks_done = conn.execute(
        "SELECT COUNT(*) c FROM work_orders WHERE business_id=%s AND status IN ('done','verified') "
        "AND COALESCE(completed_at, updated_at) >= date_trunc('month', now())", (business_id,)).fetchone()["c"]
    try:
        from ... import gbp_reviews as _gr
    except ImportError:  # pragma: no cover
        import gbp_reviews as _gr  # type: ignore
    return {
        "business": b["name"] if b else None,
        "goal": b["goal"] if b else None,
        "score": score,
        "biggest_gaps": gaps,
        "tasks_done_this_month": tasks_done,
        "local_reputation": _gr.latest(business_id),   # the Local Reputation section
    }


@router.get("/answer-lenses")
def answer_lenses(business_id: int = Depends(authorize_business)):
    """Cross-engine divergence (where engines disagree) + persona/location lens (how different
    audiences see you) — derived from the latest audit's answers."""
    try:
        from ... import lenses as _l
    except ImportError:  # pragma: no cover
        import lenses as _l  # type: ignore
    return _l.summary(business_id)


@router.get("/metrics-trend")
def metrics_trend(business_id: int = Depends(authorize_business)):
    """Per-run series of overall + per-engine reputation scores (0-100) over time, so the client
    sees each AI engine's trajectory, not just today's snapshot."""
    try:
        from ... import run_metrics as _rm
    except ImportError:  # pragma: no cover
        import run_metrics as _rm  # type: ignore
    return _rm.trend(business_id)


@router.get("/reviews")
def reviews(business_id: int = Depends(authorize_business)):
    """Current Google rating snapshot + delta + recent reviews (from the ingest_gbp_reviews job)."""
    try:
        from ... import gbp_reviews as _gr
    except ImportError:  # pragma: no cover
        import gbp_reviews as _gr  # type: ignore
    return _gr.latest(business_id)


@router.get("/activity-summary")
def activity_summary(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Client-facing 'this month's work' counts (audits, content, tasks, monitoring, outreach)
    for the current calendar month — the retention narrative that shows the needle moving.
    Per-metric counts are resilient: a missing table/column degrades that count to 0."""
    month = "date_trunc('month', now())"

    def c(sql: str) -> int:
        try:
            return conn.execute(sql, (business_id,)).fetchone()["c"]
        except Exception:  # noqa: BLE001 -- one bad count must not sink the panel
            conn.rollback()
            return 0

    return {
        "audits": c(f"SELECT COUNT(*) c FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND started_at >= {month}"),
        "drafts": c(f"SELECT COUNT(*) c FROM content_drafts WHERE business_id=%s AND created_at >= {month}"),
        "published": c(f"SELECT COUNT(*) c FROM assets WHERE business_id=%s AND COALESCE(published_at, created_at) >= {month}"),
        "tasks_done": c(f"SELECT COUNT(*) c FROM work_orders WHERE business_id=%s AND status IN ('done','verified') AND COALESCE(completed_at, updated_at) >= {month}"),
        "mentions": c(f"SELECT COUNT(*) c FROM mentions WHERE business_id=%s AND created_at >= {month}"),
        "outreach": c(f"SELECT COUNT(*) c FROM discovery_targets WHERE business_id=%s AND created_at >= {month}"),
    }


@router.get("/seo-keywords")
def seo_keywords(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """The SEO keyword-intelligence set (target_keywords) to rank for, highest priority first.
    Produced by the keyword_research job (LLM seed + Serper grounding). Distinct from
    /keywords, which is the brand-monitoring keyword list."""
    rows = conn.execute(
        "SELECT keyword, kind, source, intent, priority, rationale FROM target_keywords "
        "WHERE business_id=%s ORDER BY priority DESC NULLS LAST, keyword",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


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
