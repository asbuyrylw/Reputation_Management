"""Content & work (Phase 3): reads for the work queue + the HUMAN-GATED write actions.

Writes require editor access and wrap the verified engine functions so the human
approval gate + compliance stay enforced. The actor (reviewer/assignee) comes from
the JWT user, never the client body. Each write pre-checks the target row's
business_id matches the path (the engine functions don't check tenancy).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import authorize_business, get_conn, get_current_user, require_business_editor
from ..schemas import RejectRequest, StatusRequest


class DiscoveryTargetCreate(BaseModel):
    name: str
    channel: str = "manual"
    outlet: Optional[str] = None
    url: Optional[str] = None
    beat: Optional[str] = None
    rationale: Optional[str] = None


class TargetStatusRequest(BaseModel):
    status: str

try:
    from ... import content_generator as _cg
    from ... import tracking as _tracking
except ImportError:  # pragma: no cover
    import content_generator as _cg  # type: ignore
    import tracking as _tracking  # type: ignore

router = APIRouter(prefix="/businesses/{business_id}", tags=["content"])


def _actor(user: dict) -> str:
    return user.get("full_name") or user["email"]


def _to_float(d: dict, *keys: str) -> dict:
    for k in keys:
        if d.get(k) is not None:
            d[k] = float(d[k])
    return d


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
@router.get("/work-orders")
def work_orders(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, wo_code, title, capability, execution, phase, status, assignee, "
        "target_date, instruction, recommended_tool, result_notes, created_at "
        "FROM work_orders WHERE business_id=%s ORDER BY id",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/content-drafts")
def content_drafts(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, work_order_id, asset_type, title, body, target_query, quality_score, "
        "quality_notes, compliance_pass, compliance_flags, status, revision_count, "
        "reviewer, reviewed_at, created_at "
        "FROM content_drafts WHERE business_id=%s ORDER BY id DESC",
        (business_id,),
    ).fetchall()
    return [_to_float(dict(r), "quality_score") for r in rows]


@router.get("/production-briefs")
def production_briefs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, platform, title, target_query, brief, status, created_at "
        "FROM production_briefs WHERE business_id=%s AND status='to_produce' ORDER BY channel, id",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/discovery-targets")
def discovery_targets(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, name, outlet, url, beat, score, rationale, status, created_at "
        "FROM discovery_targets WHERE business_id=%s ORDER BY score DESC NULLS LAST, id",
        (business_id,),
    ).fetchall()
    return [_to_float(dict(r), "score") for r in rows]


@router.get("/assets")
def assets(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Finalized / published content — assets created when a draft is approved or a
    produced piece is logged. The approved draft's body is attached when available."""
    rows = conn.execute(
        "SELECT a.id, a.asset_type, a.title, a.url, a.surface, a.published_at, a.work_order_id, "
        "d.body, d.target_query "
        "FROM assets a "
        "LEFT JOIN content_drafts d ON d.work_order_id = a.work_order_id AND d.status='approved' "
        "WHERE a.business_id=%s ORDER BY a.published_at DESC NULLS LAST, a.id DESC",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/discovery-targets", status_code=201)
def add_discovery_target(
    payload: DiscoveryTargetCreate,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    """Manually add an outreach target (in addition to the ones the Discovery agent finds)."""
    row = conn.execute(
        "INSERT INTO discovery_targets (business_id, channel, name, outlet, url, beat, rationale, status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'suggested') RETURNING id",
        (business_id, payload.channel, payload.name, payload.outlet, payload.url, payload.beat, payload.rationale),
    ).fetchone()
    conn.commit()
    return {"id": row["id"]}


@router.post("/discovery-targets/{target_id}/status")
def set_discovery_status(
    target_id: int,
    body: TargetStatusRequest,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    r = conn.execute(
        "UPDATE discovery_targets SET status=%s WHERE id=%s AND business_id=%s RETURNING id",
        (body.status, target_id, business_id),
    ).fetchone()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    conn.commit()
    return {"id": target_id, "status": body.status}


# ---------------------------------------------------------------------------
# Write actions (editor-only; human gate preserved)
# ---------------------------------------------------------------------------
def _assert_draft_in_business(conn, draft_id: int, business_id: int) -> None:
    row = conn.execute("SELECT business_id FROM content_drafts WHERE id=%s", (draft_id,)).fetchone()
    if not row or row["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")


@router.post("/content-drafts/{draft_id}/approve")
def approve_draft(
    draft_id: int,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    _assert_draft_in_business(conn, draft_id, business_id)
    _cg.approve(draft_id, _actor(user))   # promotes draft -> assets, advances the work order
    return {"ok": True, "draft_id": draft_id, "status": "approved"}


@router.post("/content-drafts/{draft_id}/reject")
def reject_draft(
    draft_id: int,
    body: RejectRequest,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    _assert_draft_in_business(conn, draft_id, business_id)
    _cg.reject(draft_id, _actor(user), body.notes)
    return {"ok": True, "draft_id": draft_id, "status": "rejected"}


@router.post("/work-orders/{wo_id}/status")
def set_work_order_status(
    wo_id: int,
    body: StatusRequest,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    if body.status not in _tracking.VALID_STATUS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"status must be one of {sorted(_tracking.VALID_STATUS)}",
        )
    row = conn.execute("SELECT business_id FROM work_orders WHERE id=%s", (wo_id,)).fetchone()
    if not row or row["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    _tracking.set_status(wo_id, body.status, body.assignee, body.notes)
    return {"ok": True, "wo_id": wo_id, "status": body.status}
