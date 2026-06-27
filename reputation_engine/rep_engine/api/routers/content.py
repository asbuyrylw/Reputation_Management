"""Content & work (Phase 3): reads for the work queue + the HUMAN-GATED write actions.

Writes require editor access and wrap the verified engine functions so the human
approval gate + compliance stay enforced. The actor (reviewer/assignee) comes from
the JWT user, never the client body. Each write pre-checks the target row's
business_id matches the path (the engine functions don't check tenancy).
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .. import jobs as _jobs
from ..deps import authorize_business, get_conn, get_current_user, require_business_editor
from ..schemas import RejectRequest, StatusRequest
from ..settings import api_settings


class DiscoveryTargetCreate(BaseModel):
    name: str
    channel: str = "manual"
    outlet: Optional[str] = None
    url: Optional[str] = None
    beat: Optional[str] = None
    rationale: Optional[str] = None
    target_type: Optional[str] = None
    capabilities: Optional[list[str]] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class DiscoveryTargetUpdate(BaseModel):
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    target_type: Optional[str] = None
    capabilities: Optional[list[str]] = None


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
        "target_date, instruction, recommended_tool, result_notes, created_at, "
        "rationale, gap_source, why_helps_ai_rep, why_helps_seo, added_in_revision, "
        "start_date, predicted_ai_points, predicted_seo_impact, predicted_basis, area, platform, "
        "completed_at, "
        "COALESCE(superseded, false) AS superseded, "
        "COALESCE(planned, false) AS planned, promoted_at, assignee_user_id, "
        "COALESCE(progress_notes, '[]'::jsonb) AS progress_notes "
        "FROM work_orders WHERE business_id=%s ORDER BY id",
        (business_id,),
    ).fetchall()
    return [_to_float(dict(r), "predicted_ai_points") for r in rows]


class WorkOrderCreate(BaseModel):
    title: str
    instruction: Optional[str] = None
    recommended_tool: Optional[str] = None
    target_date: Optional[str] = None


@router.post("/work-orders", status_code=201)
def add_work_order(payload: WorkOrderCreate, business_id: int = Depends(require_business_editor)):
    """Manually add an ad-hoc task to the work queue (outside the generated plan)."""
    from ... import tracking as _t
    try:
        wid = _t.create_work_order(business_id, payload.title, instruction=payload.instruction,
                                   recommended_tool=payload.recommended_tool,
                                   target_date=payload.target_date)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"id": wid}


@router.get("/team")
def team(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """People who can be assigned tasks on this business (org members + business-access editors +
    platform admins) — powers the FK-backed assignee dropdown so assignees stop fragmenting."""
    rows = conn.execute(
        "SELECT DISTINCT u.id, u.full_name, u.email FROM users u WHERE u.is_active AND ("
        " u.org_id = (SELECT org_id FROM businesses WHERE id=%s)"
        " OR u.id IN (SELECT user_id FROM business_access WHERE business_id=%s)"
        " OR u.role='admin') ORDER BY u.full_name NULLS LAST, u.email",
        (business_id, business_id),
    ).fetchall()
    return [{"id": r["id"], "name": r["full_name"] or r["email"], "email": r["email"]} for r in rows]


@router.get("/content-drafts")
def content_drafts(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT d.id, d.work_order_id, d.asset_type, d.title, d.body, d.target_query, "
        "d.quality_score, d.quality_notes, d.compliance_pass, d.compliance_flags, d.status, "
        "d.revision_count, d.reviewer, d.reviewed_at, d.created_at, "
        "d.highlighted_sections, d.placeholders_pending, w.instruction AS wo_instruction "
        "FROM content_drafts d LEFT JOIN work_orders w ON w.id = d.work_order_id "
        "WHERE d.business_id=%s ORDER BY d.id DESC",
        (business_id,),
    ).fetchall()
    return [_to_float(dict(r), "quality_score") for r in rows]


@router.get("/production-briefs")
def production_briefs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, platform, title, target_query, brief, status, created_at, "
        "amplification_playbook, why_helps_ai_rep, why_helps_seo "
        "FROM production_briefs WHERE business_id=%s AND status='to_produce' ORDER BY channel, id",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _csv_response(rows: list[dict], columns: list[str], filename: str) -> Response:
    """Render rows to a CSV download (only the given columns, in order)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow(["" if r.get(c) is None else str(r.get(c)) for c in columns])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/production-briefs/export")
def export_production_briefs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Export every content-to-produce brief as CSV so the work can be handed to someone to do
    outside the platform. Includes the why-it-helps rationale + the structured brief as text."""
    rows = conn.execute(
        "SELECT id, channel, platform, title, target_query, status, why_helps_ai_rep, why_helps_seo, "
        "amplification_playbook, brief, created_at "
        "FROM production_briefs WHERE business_id=%s AND status IN ('to_produce','in_production') "
        "ORDER BY channel, id", (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        b = d.get("brief")
        d["brief"] = (b if isinstance(b, str) else __import__("json").dumps(b)) if b else ""
        out.append(d)
    cols = ["id", "channel", "platform", "title", "target_query", "status",
            "why_helps_ai_rep", "why_helps_seo", "amplification_playbook", "brief", "created_at"]
    return _csv_response(out, cols, "content-to-produce.csv")


@router.get("/work-orders/export")
def export_work_orders(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Export the task board (work orders) as CSV for tracking / handoff outside the platform."""
    rows = conn.execute(
        "SELECT id, wo_code, title, capability, phase, status, assignee, target_date, "
        "completed_at, instruction, recommended_tool FROM work_orders "
        "WHERE business_id=%s ORDER BY status, phase, id", (business_id,),
    ).fetchall()
    cols = ["id", "wo_code", "title", "capability", "phase", "status", "assignee", "target_date",
            "completed_at", "recommended_tool", "instruction"]
    return _csv_response([dict(r) for r in rows], cols, "tasks.csv")


@router.get("/actions-taken")
def actions_taken(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """The log of work actually completed (tasks + content), with real dates -- the 'what we did
    between audits' record that the impact loop correlates to score movement."""
    rows = conn.execute(
        "SELECT id, source, capability, area, platform, title, completed_on, logged_at, logged_by, "
        "work_order_id, production_brief_id, notes FROM actions_taken "
        "WHERE business_id=%s ORDER BY completed_on DESC, id DESC", (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/social-audit")
def social_audit(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """Per-platform owned-social posture: discovered profiles (website-confirmed vs inferred vs the
    Google Business Profile), completeness, and concrete improvement recommendations (Phase B)."""
    rows = conn.execute(
        'SELECT platform, "exists" AS exists, profile_url, source, confidence, completeness, audit, '
        "last_checked_at FROM social_presence WHERE business_id=%s ORDER BY "
        '("exists") DESC, platform', (business_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["completeness"] = float(d["completeness"]) if d["completeness"] is not None else None
        out.append(d)
    return out


@router.get("/task-impact")
def task_impact(business_id: int = Depends(authorize_business)):
    """'Which task types moved the needle most' -- correlates completed actions (between audits) to
    the goal-alignment score change. Correlation, not proof; confidence rises with more audits."""
    try:
        from ... import feedback_loop as _fb
    except ImportError:  # pragma: no cover
        import feedback_loop as _fb  # type: ignore
    return _fb.task_impact(business_id)


@router.get("/discovery-targets")
def discovery_targets(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, name, outlet, url, beat, score, rationale, status, created_at, "
        "target_type, capabilities, contact_name, contact_email, contact_phone, contact_verified "
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
        "a.published_url, a.published_status, a.summary, d.body, d.target_query "
        "FROM assets a "
        "LEFT JOIN content_drafts d ON d.work_order_id = a.work_order_id AND d.status='approved' "
        "WHERE a.business_id=%s ORDER BY a.published_at DESC NULLS LAST, a.id DESC",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- multi-surface distribution log (where each asset was posted) ---
@router.get("/assets/{asset_id}/placements")
def asset_placements(asset_id: int, business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, channel, status, url, published_at FROM asset_placements "
        "WHERE asset_id=%s AND business_id=%s ORDER BY id", (asset_id, business_id),
    ).fetchall()
    return [dict(r) for r in rows]


class PlacementCreate(BaseModel):
    channel: str


@router.post("/assets/{asset_id}/placements", status_code=201)
def add_placement(asset_id: int, body: PlacementCreate, business_id: int = Depends(require_business_editor),
                  conn=Depends(get_conn)):
    """Add a channel this asset should be distributed to (the per-surface checklist)."""
    row = conn.execute("SELECT business_id FROM assets WHERE id=%s", (asset_id,)).fetchone()
    if not row or row["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    ch = (body.channel or "").strip()
    if not ch:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "channel required")
    r = conn.execute(
        "INSERT INTO asset_placements (business_id, asset_id, channel) VALUES (%s,%s,%s) "
        "ON CONFLICT (asset_id, channel) DO NOTHING RETURNING id", (business_id, asset_id, ch),
    ).fetchone()
    conn.commit()
    return {"id": r["id"] if r else None, "channel": ch}


class PlacementUpdate(BaseModel):
    status: Optional[str] = None   # planned | published | skipped
    url: Optional[str] = None


@router.patch("/placements/{placement_id}")
def update_placement(placement_id: int, body: PlacementUpdate,
                     business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Mark a placement published (with its live URL) or skipped."""
    sets, params = ["status=COALESCE(%s, status)"], [body.status]
    if body.url is not None:
        sets.append("url=%s"); params.append(body.url.strip() or None)
    if (body.status or "") == "published":
        sets.append("published_at=COALESCE(published_at, now())")
    params += [placement_id, business_id]
    r = conn.execute(
        f"UPDATE asset_placements SET {', '.join(sets)} WHERE id=%s AND business_id=%s RETURNING id",  # nosec B608
        params,
    ).fetchone()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Placement not found")
    conn.commit()
    return {"id": placement_id}


class AssetPublishUpdate(BaseModel):
    published_url: Optional[str] = None
    published_status: Optional[str] = None   # 'pending' | 'live'


@router.patch("/assets/{asset_id}")
def update_asset(
    asset_id: int,
    body: AssetPublishUpdate,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    """Record WHERE a finalized asset was published (manual link entry, since there's no live
    site/social integration yet) and flip its status pending -> live."""
    fields: dict = {}
    if body.published_url is not None:
        fields["published_url"] = body.published_url.strip()
        # entering a link implies it's live, unless the caller says otherwise
        fields["published_status"] = (body.published_status or "live").strip()
    elif body.published_status is not None:
        fields["published_status"] = body.published_status.strip()
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nothing to update")
    set_clause = ", ".join(f"{k}=%s" for k in fields)  # keys are fixed literals above
    params = list(fields.values()) + [asset_id, business_id]
    row = conn.execute(
        f"UPDATE assets SET {set_clause} WHERE id=%s AND business_id=%s RETURNING id",  # nosec B608
        params,
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    conn.commit()
    return {"id": asset_id, **fields}


@router.post("/discovery-targets", status_code=201)
def add_discovery_target(
    payload: DiscoveryTargetCreate,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    """Manually add an outreach target (in addition to the ones the Discovery agent finds)."""
    row = conn.execute(
        "INSERT INTO discovery_targets (business_id, channel, name, outlet, url, beat, rationale, "
        "status, target_type, capabilities, contact_name, contact_email, contact_phone, contact_verified) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'suggested',%s,%s,%s,%s,%s,%s) RETURNING id",
        (business_id, payload.channel, payload.name, payload.outlet, payload.url, payload.beat,
         payload.rationale, payload.target_type, payload.capabilities,
         payload.contact_name, payload.contact_email, payload.contact_phone,
         bool(payload.contact_name or payload.contact_email or payload.contact_phone)),
    ).fetchone()
    conn.commit()
    return {"id": row["id"]}


@router.patch("/discovery-targets/{target_id}")
def update_discovery_target(
    target_id: int,
    body: DiscoveryTargetUpdate,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    """Edit an outreach target's contact info / type / capabilities (manual override of what the
    discovery agent found). Setting any contact field marks the contact as verified (you entered it)."""
    fields: dict = {}
    for k in ("contact_name", "contact_email", "contact_phone", "target_type", "capabilities"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nothing to update")
    if any(k.startswith("contact_") for k in fields):
        fields["contact_verified"] = True
    set_clause = ", ".join(f"{k}=%s" for k in fields)  # keys are fixed literals
    params = list(fields.values()) + [target_id, business_id]
    row = conn.execute(
        f"UPDATE discovery_targets SET {set_clause} WHERE id=%s AND business_id=%s RETURNING id",  # nosec B608
        params,
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    conn.commit()
    return {"id": target_id, **fields}


@router.post("/discovery-targets/{target_id}/push")
def push_target(target_id: int, business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Push an outreach target out to the client's stack (GoHighLevel/Zapier/...) via the webhook
    bus — turns a target into a CRM opportunity. No-op (returns sent=false) until WEBHOOK_URL is set."""
    t = conn.execute(
        "SELECT name, outlet, url, beat, contact_name, contact_email, contact_phone, target_type, capabilities "
        "FROM discovery_targets WHERE id=%s AND business_id=%s", (target_id, business_id)).fetchone()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    try:
        from ... import webhooks as _wh
    except ImportError:  # pragma: no cover
        import webhooks as _wh  # type: ignore
    sent = _wh.enabled()
    _wh.emit(business_id, "outreach.target", {"target_id": target_id, **{k: t[k] for k in t.keys()}})
    return {"sent": sent}


class PitchRequest(BaseModel):
    pass


@router.post("/discovery-targets/{target_id}/draft-pitch")
def draft_pitch(target_id: int, business_id: int = Depends(require_business_editor), conn=Depends(get_conn)):
    """Draft a short, human-reviewed outreach pitch for a target (the operator edits + sends it)."""
    t = conn.execute(
        "SELECT name, outlet, beat, target_type, capabilities FROM discovery_targets "
        "WHERE id=%s AND business_id=%s", (target_id, business_id)).fetchone()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target not found")
    b = conn.execute("SELECT name, services, geo, goal FROM businesses WHERE id=%s", (business_id,)).fetchone()
    try:
        from ... import ai_state_audit as _llm
    except ImportError:  # pragma: no cover
        import ai_state_audit as _llm  # type: ignore
    system = ("You write concise, genuine outreach pitches (4-6 sentences) to journalists/outlets/"
              "podcasts to earn a mention or feature. Warm, specific, no fluff or false claims. "
              "Output ONLY the pitch (subject line + body), no preamble.")
    ctx = (f"From: {b['name']} ({b.get('services','')}) in {b.get('geo','')}. Goal: {b.get('goal','')}.\n"
           f"To: {t['name']} at {t.get('outlet','')} — covers {t.get('beat','')} ({t.get('target_type','')}).\n"
           "Write a pitch proposing a relevant story/contribution that would interest their audience.")
    pitch = (_llm.orchestrator_text(system, ctx, max_tokens=500, tier="mid") or "").strip()
    if not pitch:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Drafting is unavailable right now.")
    return {"pitch": pitch}


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


class DraftEdit(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None


@router.patch("/content-drafts/{draft_id}")
def edit_draft(
    draft_id: int,
    payload: DraftEdit,
    business_id: int = Depends(require_business_editor),
    conn=Depends(get_conn),
):
    """Revise a draft's title/body before approving it (fix a fact, adjust tone). Editable
    only while it's still a draft -- an already-approved/published one is immutable (409)."""
    _assert_draft_in_business(conn, draft_id, business_id)
    ok = _cg.update_draft(draft_id, title=payload.title, body=payload.body, business_id=business_id)
    if not ok:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Draft can't be edited (already approved/published, or nothing to change)")
    return {"updated": draft_id}


class ApproveRequest(BaseModel):
    override_reason: Optional[str] = None


@router.post("/content-drafts/{draft_id}/approve")
def approve_draft(
    draft_id: int,
    body: ApproveRequest = ApproveRequest(),
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    _assert_draft_in_business(conn, draft_id, business_id)
    try:
        # promotes draft -> assets, advances the work order, records an immutable compliance sign-off
        _cg.approve(draft_id, _actor(user), override_reason=body.override_reason)
    except ValueError as e:  # compliance gate / not-approvable -> 422, not a 500
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    # Close the publish loop (#2c): approving an asset enqueues a publish sweep so it flows to the
    # owner's connected channels automatically. Fully gated -- the sweep is a keyless no-op without
    # a connection, and AUTOPOST_GLOBAL_ENABLED still governs whether anything actually posts -- so
    # this never publishes anything the owner hasn't enabled.
    queued = None
    try:
        if "publish_sweep" in _jobs.JOB_DISPATCH and _jobs.rate_ok(business_id, "publish_sweep"):
            queued, _active = _jobs.enqueue(business_id, "publish_sweep", requested_by=user["id"])
    except Exception:  # noqa: BLE001 -- approval must succeed even if the sweep can't be queued
        queued = None
    return {"ok": True, "draft_id": draft_id, "status": "approved", "publish_job": queued}


@router.get("/compliance-ledger")
def compliance_ledger(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    """The immutable compliance sign-off record (who approved what, when, with which verdict) —
    the audit trail a broker-dealer/RIA principal review requires."""
    rows = conn.execute(
        "SELECT cs.id, cs.draft_id, cs.asset_id, cs.approver, cs.compliance_pass, "
        "cs.compliance_flags, cs.override_reason, cs.body_hash, cs.signed_at, "
        "COALESCE(d.title, a.title) AS title "
        "FROM compliance_signoffs cs "
        "LEFT JOIN content_drafts d ON d.id = cs.draft_id "
        "LEFT JOIN assets a ON a.id = cs.asset_id "
        "WHERE cs.business_id=%s ORDER BY cs.signed_at DESC LIMIT 100",
        (business_id,),
    ).fetchall()
    return [dict(r) for r in rows]


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
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    if body.status not in _tracking.VALID_STATUS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"status must be one of {sorted(_tracking.VALID_STATUS)}",
        )
    if body.completed_on:
        try:
            date.fromisoformat(body.completed_on)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "completed_on must be YYYY-MM-DD")
    row = conn.execute("SELECT business_id FROM work_orders WHERE id=%s", (wo_id,)).fetchone()
    if not row or row["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    # completed_on lets an operator mark a task done on its REAL date even if the work happened
    # outside the platform; set_status logs it to actions_taken for the impact-learning loop.
    _tracking.set_status(wo_id, body.status, body.assignee, body.notes,
                         completed_on=body.completed_on, actor=_actor(user))
    return {"ok": True, "wo_id": wo_id, "status": body.status, "completed_on": body.completed_on}


class BriefStatusRequest(BaseModel):
    status: str = "produced"            # to_produce | in_production | produced | superseded
    produced_on: Optional[str] = None   # YYYY-MM-DD (may be back-dated); defaults to today on 'produced'


_BRIEF_STATUS = {"to_produce", "in_production", "produced", "superseded"}


@router.post("/production-briefs/{brief_id}/status")
def set_production_brief_status(
    brief_id: int,
    body: BriefStatusRequest,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    """Mark a content-to-produce brief in_production / produced (with a real, back-datable date) /
    superseded. Marking it 'produced' logs an action so completing it counts toward impact even
    when the content was made outside the platform."""
    if body.status not in _BRIEF_STATUS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {sorted(_BRIEF_STATUS)}")
    pon = None
    if body.produced_on:
        try:
            pon = date.fromisoformat(body.produced_on)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "produced_on must be YYYY-MM-DD")
    brief = conn.execute(
        "SELECT business_id, channel, platform, title FROM production_briefs WHERE id=%s", (brief_id,),
    ).fetchone()
    if not brief or brief["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brief not found")
    if body.status == "produced":
        pon = pon or date.today()
        conn.execute("UPDATE production_briefs SET status='produced', produced_on=%s WHERE id=%s",
                     (pon, brief_id))
        _tracking.log_action(conn, business_id=business_id, capability="content_production",
                             title=brief["title"], completed_on=pon, production_brief_id=brief_id,
                             source="brief", area="social" if brief["channel"] == "social" else brief["channel"],
                             platform=brief["platform"], logged_by=_actor(user))
    else:
        conn.execute("UPDATE production_briefs SET status=%s WHERE id=%s", (body.status, brief_id))
        if body.status in ("to_produce", "in_production"):  # reverted -> drop any logged action
            conn.execute("DELETE FROM actions_taken WHERE production_brief_id=%s", (brief_id,))
    conn.commit()
    return {"ok": True, "brief_id": brief_id, "status": body.status, "produced_on": str(pon) if pon else None}


def _resolve_assignee(conn, assignee_user_id: Optional[int]) -> Optional[str]:
    """Map a team-member user id to a display name (for the FK-backed assignee dropdown)."""
    if not assignee_user_id:
        return None
    r = conn.execute("SELECT full_name, email FROM users WHERE id=%s", (assignee_user_id,)).fetchone()
    return (r["full_name"] or r["email"]) if r else None


class WorkOrderEdit(BaseModel):
    assignee: Optional[str] = None
    assignee_user_id: Optional[int] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None


@router.patch("/work-orders/{wo_id}")
def edit_work_order(
    wo_id: int,
    body: WorkOrderEdit,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    """Assign a task to someone and set its start / due dates (so the owner sees who's
    responsible for what, by when). Empty string clears a field."""
    fields: dict = {}
    # FK-backed assignment (preferred): set the user id + the display name from the roster.
    if body.assignee_user_id is not None:
        fields["assignee_user_id"] = body.assignee_user_id or None
        fields["assignee"] = _resolve_assignee(conn, body.assignee_user_id)
    elif body.assignee is not None:
        fields["assignee"] = body.assignee.strip() or None
    for k in ("start_date", "target_date"):
        v = getattr(body, k)
        if v is not None:
            v = v.strip()
            try:
                fields[k] = date.fromisoformat(v) if v else None
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k} must be YYYY-MM-DD")
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nothing to update")
    set_clause = ", ".join(f"{k}=%s" for k in fields) + ", updated_at=now()"  # keys are fixed literals
    params = list(fields.values()) + [wo_id, business_id]
    row = conn.execute(
        f"UPDATE work_orders SET {set_clause} WHERE id=%s AND business_id=%s RETURNING id, title",  # nosec B608
        params,
    ).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    conn.commit()
    # Alert the assignee they were given a task (skip self-assignment). User-targeted + emailed when
    # SMTP is configured; deduped per (task, user) so re-saving doesn't re-notify.
    assignee_uid = fields.get("assignee_user_id")
    if assignee_uid and assignee_uid != user.get("id"):
        try:
            from ... import notifications as _notify
        except ImportError:  # pragma: no cover
            import notifications as _notify  # type: ignore
        try:
            _notify.notify_user(
                business_id, assignee_uid, "task_assigned",
                f"You were assigned: {row['title'] or 'a task'}",
                f"{_actor(user)} assigned you this task"
                + (f", due {fields['target_date']}" if fields.get("target_date") else "") + ".",
                severity="info", dedup_key=f"assigned_wo_{wo_id}_u{assignee_uid}")
        except Exception as e:  # noqa: BLE001 -- assignment must succeed even if alerting fails
            pass
    return {"id": wo_id, **fields}


class WorkOrderPromote(BaseModel):
    assignee: Optional[str] = None
    assignee_user_id: Optional[int] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    note: Optional[str] = None


@router.post("/work-orders/{wo_id}/promote")
def promote_work_order(
    wo_id: int,
    body: WorkOrderPromote,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    """Promote a recommendation (from 'Do this next') onto the managed 'Improvement tasks'
    board, capturing the owner + start/due dates + an optional first progress note."""
    for k in ("start_date", "target_date"):
        v = getattr(body, k)
        if v:
            try:
                date.fromisoformat(v.strip())
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k} must be YYYY-MM-DD")
    # Prefer the FK-backed assignee (resolve its display name); fall back to free text.
    assignee = _resolve_assignee(conn, body.assignee_user_id) if body.assignee_user_id else body.assignee
    ok = _tracking.promote_work_order(
        wo_id, business_id, assignee=assignee, assignee_user_id=body.assignee_user_id,
        start_date=body.start_date, target_date=body.target_date, note=body.note, actor=_actor(user),
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    return {"ok": True, "wo_id": wo_id, "planned": True}


class WorkOrderNote(BaseModel):
    text: str


@router.post("/work-orders/{wo_id}/note")
def add_work_order_note(
    wo_id: int,
    body: WorkOrderNote,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
):
    """Append a progress note to a managed task's timeline."""
    try:
        ok = _tracking.add_progress_note(wo_id, business_id, body.text, author=_actor(user))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    return {"ok": True, "wo_id": wo_id}


@router.post("/work-orders/{wo_id}/generate-draft", status_code=202)
def generate_draft_for_wo(
    wo_id: int,
    background: BackgroundTasks,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    """Generate an AI content draft for a SINGLE content work order (the per-item
    'Generate draft' button). Runs as a background job (never inline) so the LLM spend stays
    out of the request path; the draft then shows up in the review queue."""
    row = conn.execute(
        "SELECT business_id, capability, execution FROM work_orders WHERE id=%s", (wo_id,)
    ).fetchone()
    if not row or row["business_id"] != business_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Work order not found")
    if not _jobs.rate_ok(business_id, "generate_drafts"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Generating drafts too often — give it a little while and try again.")
    job_id, active = _jobs.enqueue(
        business_id, "generate_drafts", requested_by=user["id"], args={"only_wo": wo_id}
    )
    if job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"a draft-generation job is already running (#{active})")
    if api_settings().job_worker == "inline":
        background.add_task(_jobs.run_job, job_id)
    return JSONResponse(
        status_code=202, content={"job_id": job_id, "job_type": "generate_drafts", "status": "queued"}
    )
