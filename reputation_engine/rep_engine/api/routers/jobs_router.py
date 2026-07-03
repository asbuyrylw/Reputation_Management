"""Background-job triggers + status (Phase 5).

Triggering engine work (audit/cycle/...) NEVER runs it inline: it enqueues an
api_jobs row and (in inline dev mode) schedules a BackgroundTask, or leaves it for
the worker process. Progress is polled via the job row + runstate.runs_status
(pipeline_runs/pipeline_steps for cycle/run). Editor-only to trigger.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import auth as _auth
from .. import job_deps as _job_deps
from .. import jobs as _jobs
from ..deps import authorize_business, get_conn, get_current_user, require_business_editor
from ..settings import api_settings

try:
    from ... import billing as _billing
    from ... import runstate as _runstate
    from ... import scheduler as _scheduler
except ImportError:  # pragma: no cover
    import billing as _billing  # type: ignore
    import runstate as _runstate  # type: ignore
    import scheduler as _scheduler  # type: ignore

router = APIRouter(tags=["jobs"])


class ScheduleUpsert(BaseModel):
    job_type: str
    interval_hours: int
    enabled: bool = True


@router.post("/businesses/{business_id}/jobs/run-everything")
def run_everything(
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    """Enqueue the ENTIRE pipeline at once — audit, site crawl, gap analysis, plan, sync,
    AI citations, competitor benchmark, local rankings, prompts, mentions, discovery, content
    briefs, and the report — in dependency order. The expensive, one-button refresh.

    Billing-gated on the audit (the metered driver) and rate-limited to once per day so a
    stray click can't run up ~$8-12 of LLM/search spend repeatedly.

    NOTE: this literal route MUST be declared before the `/jobs/{job_type}` param route below,
    or Starlette matches `{job_type}="run-everything"` first and 400s with 'unknown job_type'."""
    ok, reason, code = _billing.check_can_trigger(conn, business_id, "audit")
    if not ok:
        raise HTTPException(code, reason)
    if not _jobs.rate_ok(business_id, "run_everything"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "“Run everything” can only be started once a day — it runs the full "
                            "pipeline. Trigger individual jobs if you need a one-off refresh.")
    jobs_enqueued = _job_deps.enqueue_pipeline(business_id, requested_by=user["id"])
    return JSONResponse(status_code=202, content={"status": "queued", "jobs": jobs_enqueued})


@router.post("/businesses/{business_id}/jobs/{job_type}")
def trigger_job(
    job_type: str,
    background: BackgroundTasks,
    business_id: int = Depends(require_business_editor),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    if job_type not in _jobs.JOB_DISPATCH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unknown job_type; one of {sorted(_jobs.JOB_DISPATCH)}",
        )
    # Billing/quota gate: blocks LLM-spending work when the org's subscription is inactive
    # or over its monthly audit quota. No org / no subscription => unmetered (legacy).
    ok, reason, code = _billing.check_can_trigger(conn, business_id, job_type)
    if not ok:
        raise HTTPException(code, reason)
    # Per-(business, job_type) rate limit so a stuck finger can't run up LLM/search spend.
    if not _jobs.rate_ok(business_id, job_type):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You're triggering {job_type} too often — give it a little while and try again.")
    job_id, active = _jobs.enqueue(business_id, job_type, requested_by=user["id"])
    if job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"a {job_type} job is already running (#{active})")
    # Auto-chain downstream jobs so one click does the whole expected thing: e.g. "Regenerate
    # plan" also materializes work-orders (sync_plan) + content-to-produce (production_briefs).
    # Children carry depends_on=[parent], so the worker runs them in order; dedup prevents
    # double-runs. (In inline dev mode only the root runs here; the worker pumps the chain.)
    chained = _job_deps.enqueue_downstream(business_id, job_type, job_id, requested_by=user["id"])
    if api_settings().job_worker == "inline":
        background.add_task(_jobs.run_job, job_id)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "job_type": job_type, "status": "queued", "chained": chained},
    )


@router.get("/businesses/{business_id}/jobs")
def list_jobs(business_id: int = Depends(authorize_business), conn=Depends(get_conn)):
    rows = conn.execute(
        "SELECT id, job_type, status, error, result, created_at, started_at, finished_at "
        "FROM api_jobs WHERE business_id=%s ORDER BY id DESC LIMIT 20",
        (business_id,),
    ).fetchall()
    return {"jobs": [dict(r) for r in rows], "pipeline_runs": _runstate.runs_status(business_id)}


@router.get("/businesses/{business_id}/schedules")
def list_schedules(business_id: int = Depends(authorize_business)):
    """Recurring automation for this business (what runs, how often, when next)."""
    return _scheduler.list_schedules(business_id)


@router.post("/businesses/{business_id}/schedules")
def upsert_schedule(payload: ScheduleUpsert, business_id: int = Depends(require_business_editor)):
    try:
        return _scheduler.upsert_schedule(business_id, payload.job_type, payload.interval_hours, payload.enabled)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.delete("/businesses/{business_id}/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, business_id: int = Depends(require_business_editor)):
    if not _scheduler.delete_schedule(business_id, schedule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return {"deleted": schedule_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: dict = Depends(get_current_user), conn=Depends(get_conn)):
    job = conn.execute("SELECT * FROM api_jobs WHERE id=%s", (job_id,)).fetchone()
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    if user["role"] != "admin":
        # Org-aware tenancy: org owners/managers + business_access members can see the job.
        # (The old check only honored a direct business_access row, denying org owners.)
        if job["business_id"] not in (_auth.accessible_business_ids(conn, user) or []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this job")
    return dict(job)
