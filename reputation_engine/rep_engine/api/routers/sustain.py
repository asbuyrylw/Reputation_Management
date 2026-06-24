"""Timeline / acceleration / sustain (Phase 4): the projection, what-if acceleration
scenarios, learned lever effectiveness, incidents + mentions, and the alert check.
All reads are pure (estimate/advise/momentum do no LLM + no writes). The one write
is resuming a human-gated incident review, which requires the durable checkpointer.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, require_business_editor
from ..schemas import ResumeRequest


class KeywordCreate(BaseModel):
    keyword: str
    negative: bool = False

try:
    from ... import acceleration_advisor as _acc
    from ... import challenge as _challenge
    from ... import feedback_loop as _fb
    from ... import local_seo_goals as _lsg
    from ... import timeline_estimator as _te
    from ... import tracking as _tracking
except ImportError:  # pragma: no cover
    import acceleration_advisor as _acc  # type: ignore
    import challenge as _challenge  # type: ignore
    import feedback_loop as _fb  # type: ignore
    import local_seo_goals as _lsg  # type: ignore
    import timeline_estimator as _te  # type: ignore
    import tracking as _tracking  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["sustain"])


@router.get("/timeline")
def timeline(business_id: int = Depends(authorize_business)):
    return _te.estimate(business_id, quiet=True)


@router.get("/local-seo-goal")
def local_seo_goal(business_id: int = Depends(authorize_business)):
    """Projected time to reach page 1 of Google for the local category searches (read-only)."""
    return _lsg.estimate(business_id, quiet=True, persist=False)


@router.get("/challenge")
def challenge(business_id: int = Depends(authorize_business)):
    """Primary-challenge profile: is this an awareness gap (a void to fill, faster) or
    an entrenched negative narrative (slower to crowd out)? Pure read."""
    return _challenge.challenge_profile(business_id, quiet=True)


@router.get("/acceleration")
def acceleration(business_id: int = Depends(authorize_business)):
    return _acc.advise(business_id, quiet=True)


@router.get("/learned-levers")
def learned_levers(business_id: int = Depends(authorize_business)):
    monthly_gain, confidence = _fb.learned_baseline(business_id)
    # predicted_levers = the industry-baseline per-unit gain in SCORE POINTS (the plan's estimate);
    # levers = what we've actually MEASURED from this business -> the predicted-vs-actual view.
    predicted = {k: round((v.get("weight", 0) or 0) * 100, 2) for k, v in _acc.LEVERS.items()}
    return {
        "baseline": {"monthly_gain": monthly_gain, "confidence": confidence},
        "levers": _fb.learned_lever_weights(business_id),
        "predicted_levers": predicted,
    }


@router.get("/alert")
def alert(business_id: int = Depends(authorize_business)):
    return _tracking.check_alert(business_id)


@router.get("/incidents")
def incidents(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, mention_url, sentiment, severity, severity_score, delay_impact, "
        "draft_response, sla_hours, status, created_at, resolved_at "
        "FROM incidents WHERE business_id=%s ORDER BY id DESC LIMIT 100",
        (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["severity_score"] = float(d["severity_score"]) if d["severity_score"] is not None else None
        out.append(d)
    return out


@router.get("/notifications")
def list_notifications(business_id: int = Depends(authorize_business), unread_only: bool = False):
    from ... import notifications as _n
    return {"items": _n.list_notifications(business_id, unread_only=unread_only),
            "unread": _n.unread_count(business_id)}


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, business_id: int = Depends(require_business_editor)):
    from ... import notifications as _n
    if not _n.mark_read(business_id, notification_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return {"read": notification_id}


@router.post("/notifications/read-all")
def read_all_notifications(business_id: int = Depends(require_business_editor)):
    from ... import notifications as _n
    return {"read": _n.mark_all_read(business_id)}


@router.get("/keywords")
def list_keywords(business_id: int = Depends(authorize_business)):
    from ... import mention_monitor as _mm
    return _mm.list_keywords(business_id)


@router.post("/keywords", status_code=201)
def add_keyword(payload: KeywordCreate, business_id: int = Depends(require_business_editor)):
    from ... import mention_monitor as _mm
    kw = payload.keyword.strip()
    if not kw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "keyword required")
    kid = _mm.add_keyword(business_id, kw, payload.negative)
    return {"id": kid, "keyword": kw, "negative": payload.negative}


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, business_id: int = Depends(require_business_editor)):
    from ... import mention_monitor as _mm
    if not _mm.remove_keyword(business_id, keyword_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keyword not found")
    return {"deleted": keyword_id}


@router.get("/mentions")
def mentions(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, source, source_url, author, title, body, matched_keyword, sentiment, "
        "relevance, status, discovered_at "
        "FROM mentions WHERE business_id=%s ORDER BY discovered_at DESC NULLS LAST, id DESC LIMIT 100",
        (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["relevance"] = float(d["relevance"]) if d["relevance"] is not None else None
        out.append(d)
    return out


@router.post("/incidents/{incident_id}/resume")
def resume_incident(
    incident_id: int,
    body: ResumeRequest,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    # The human-gate graph can only be resumed cross-process with the durable
    # PostgresSaver. Without it, an in-memory saver can't find the paused run, so we
    # refuse rather than appear to succeed.
    if os.getenv("AGENT_CHECKPOINT_PG", "").lower() not in ("1", "true", "yes"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Resuming an incident review needs AGENT_CHECKPOINT_PG=1 (durable checkpointer).",
        )
    inc = conn.execute(
        "SELECT business_id, mention_url FROM incidents WHERE id=%s", (incident_id,)
    ).fetchone()
    if not inc or inc["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    # The graph's thread_id keys off the mention's external_id; reload it by URL.
    m = conn.execute(
        "SELECT source_url, external_id FROM mentions WHERE business_id=%s AND source_url=%s "
        "ORDER BY id DESC LIMIT 1",
        (business_id, inc["mention_url"]),
    ).fetchone()
    mention = {"source_url": inc["mention_url"]}
    if m and m.get("external_id"):
        mention["external_id"] = m["external_id"]

    from ... import agent_incident as _ai   # lazy: keeps langgraph off the read path
    decision: dict = {"approved": bool(body.approved)}
    if body.edited_response is not None:
        decision["edited_response"] = body.edited_response
    try:
        _ai.resume_incident(business_id, mention, decision)
    except SystemExit as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return {"ok": True, "incident_id": incident_id, "approved": bool(body.approved)}
