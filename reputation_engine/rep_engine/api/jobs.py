"""Background job runner: enqueue engine work to api_jobs and run it OUT of the HTTP
request path. Engine functions open their own db(); audit()'s per-business advisory
lock + cost.over_budget stay the budget/concurrency backstops. run_job claims a job
atomically (UPDATE ... WHERE status='queued' RETURNING), so inline BackgroundTasks and
the worker process can't double-run the same job.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

try:
    from ..db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("rep_engine.api.jobs")


# ---------------------------------------------------------------------------
# Dispatch: job_type -> a callable(business_id, args) that runs an engine action.
# Each lazily imports its module so importing this file stays light.
# ---------------------------------------------------------------------------
def _run_audit(business_id: int, args: dict) -> None:
    try:
        from .. import ai_state_audit as m
    except ImportError:  # pragma: no cover
        import ai_state_audit as m  # type: ignore
    m.audit(business_id)


def _run_cycle(business_id: int, args: dict) -> None:
    import argparse
    try:
        from .. import orchestrator as o
    except ImportError:  # pragma: no cover
        import orchestrator as o  # type: ignore
    o.run_cycle(argparse.Namespace(business_id=business_id, resume=True))


def _run_production_briefs(business_id: int, args: dict) -> None:
    try:
        from .. import production_brief as p
    except ImportError:  # pragma: no cover
        import production_brief as p  # type: ignore
    p.plan(business_id)


def _run_citation_analyze(business_id: int, args: dict) -> None:
    try:
        from .. import citation_analytics as c
    except ImportError:  # pragma: no cover
        import citation_analytics as c  # type: ignore
    c.analyze(business_id, quiet=True)


def _run_normalize_signals(business_id: int, args: dict) -> None:
    try:
        from .. import external_signals as es
    except ImportError:  # pragma: no cover
        import external_signals as es  # type: ignore
    es.normalize_pending(business_id)


def _imp(name: str):
    """Lazy import an engine module by name (package or loose-script fallback)."""
    try:
        import importlib
        return importlib.import_module(f"..{name}", __package__)
    except Exception:  # pragma: no cover -- loose-script fallback
        import importlib
        return importlib.import_module(name)


def _run_site_crawl(business_id: int, args: dict) -> None:
    _imp("site_crawl").crawl_cmd(business_id, int(args.get("max_pages", 15)))


def _run_gap_model(business_id: int, args: dict) -> None:
    _imp("ai_state_audit").build_gap_model(business_id)


def _run_plan(business_id: int, args: dict) -> None:
    _imp("strategy_generator").plan_cmd(business_id, args.get("start"))


def _run_sync_plan(business_id: int, args: dict) -> None:
    _imp("tracking").sync_plan(business_id)


def _run_generate_drafts(business_id: int, args: dict) -> None:
    _imp("content_generator").generate(business_id)


def _run_report(business_id: int, args: dict) -> None:
    _imp("report_generator").generate(business_id)


def _run_discovery(business_id: int, args: dict) -> None:
    """Find outreach targets (journalists/outlets/podcasts/communities) via the Discovery agent."""
    _imp("agent_discovery").discover(business_id)


def _run_mentions_scan(business_id: int, args: dict) -> None:
    """Scan the configured sources for new mentions, then draft (human-gated) replies."""
    mm = _imp("mention_monitor")
    mm.discover(business_id, quiet=True)
    mm.draft_replies(business_id, quiet=True)


def _run_incident_scan(business_id: int, args: dict) -> None:
    """Triage negative mentions into incidents with drafted, human-gated responses."""
    _imp("agent_incident").scan(business_id)


def _run_learn(business_id: int, args: dict) -> None:
    """Recompute 'what's working' from this business's own audit-to-audit results."""
    _imp("feedback_loop").learn(business_id, quiet=True)


JOB_DISPATCH = {
    # core pipeline (each step individually runnable, plus the full monthly cycle)
    "audit": _run_audit,
    "site_crawl": _run_site_crawl,
    "gap_model": _run_gap_model,
    "plan": _run_plan,
    "sync_plan": _run_sync_plan,
    "generate_drafts": _run_generate_drafts,
    "report": _run_report,
    "cycle": _run_cycle,
    # monitoring + outreach + learning
    "discovery": _run_discovery,
    "mentions_scan": _run_mentions_scan,
    "incident_scan": _run_incident_scan,
    "citation_analyze": _run_citation_analyze,
    "learn": _run_learn,
    "production_briefs": _run_production_briefs,
    "normalize_signals": _run_normalize_signals,
}


def enqueue(business_id: int, job_type: str, requested_by: Optional[int] = None,
            args: Optional[dict] = None) -> tuple[Optional[int], Optional[int]]:
    """Insert a queued job unless one of the same type is already active for this
    business. Returns (job_id, active_job_id): job_id set on success; otherwise
    active_job_id of the in-flight job (so the caller can 409)."""
    if job_type not in JOB_DISPATCH:
        raise ValueError(f"unknown job_type: {job_type}")
    with db() as conn:
        active = conn.execute(
            "SELECT id FROM api_jobs WHERE business_id=%s AND job_type=%s "
            "AND status IN ('queued','running') ORDER BY id DESC LIMIT 1",
            (business_id, job_type),
        ).fetchone()
        if active:
            return None, active["id"]
        row = conn.execute(
            "INSERT INTO api_jobs (business_id, job_type, status, args, requested_by) "
            "VALUES (%s,%s,'queued',%s,%s) RETURNING id",
            (business_id, job_type, json.dumps(args or {}), requested_by),
        ).fetchone()
        conn.commit()
    return row["id"], None


def run_job(job_id: int) -> Optional[str]:
    """Atomically claim a queued job and execute it; record terminal status. Returns
    the final status, or None if the job was already claimed/finished."""
    with db() as conn:
        job = conn.execute(
            "UPDATE api_jobs SET status='running', started_at=now() "
            "WHERE id=%s AND status='queued' RETURNING *",
            (job_id,),
        ).fetchone()
        conn.commit()
    if not job:
        return None
    status, err = "complete", None
    try:
        JOB_DISPATCH[job["job_type"]](job["business_id"], job.get("args") or {})
    except Exception as e:  # noqa: BLE001 -- record failure, never crash the runner
        status, err = "failed", str(e)[:2000]
        log.warning("job %s (%s) failed: %s", job_id, job["job_type"], e)
    with db() as conn:
        conn.execute(
            "UPDATE api_jobs SET status=%s, error=%s, finished_at=now() WHERE id=%s",
            (status, err, job_id),
        )
        conn.commit()
    return status
