"""Shared job-dependency graph for background jobs.

Two views of the same pipeline:

- ``SETUP_PREREQS`` — job_type -> prerequisite job_types. Used by the onboarding
  pipeline, which enqueues the whole board at once; ``depends_on`` wires the order so it
  is correct with ANY number of workers (not just a single FIFO consumer).

- ``TRIGGER_DOWNSTREAM`` — job_type -> child job_types to auto-chain when a SINGLE job is
  triggered ad hoc from the UI. Clicking "Regenerate plan" should also materialize the
  tasks (``sync_plan``) and the content-to-produce briefs (``production_briefs``); a fresh
  ``audit`` should refresh the gap model, the plan, and the citation analysis without the
  user clicking every downstream button. Each child is enqueued with
  ``depends_on=[parent_job_id]``, so the worker runs them strictly in order and the partial
  unique index ``uq_api_jobs_active`` + ``enqueue`` dedup prevent double-runs.

Why this exists: previously the manual trigger (``jobs_router.trigger_job``) enqueued ONLY
the clicked job with no ``depends_on``, so "Regenerate plan" wrote a ``strategy_plans`` row
but never ran ``sync_plan`` — the work-orders table stayed empty and the UI looked broken.
"""

from __future__ import annotations

from typing import Optional

try:
    from . import jobs as _jobs
except ImportError:  # pragma: no cover -- loose-script fallback
    import jobs as _jobs  # type: ignore


# The full pipeline, in dependency order, so a business goes from nothing to every section
# populated in one shot. Shared by the onboarding wizard AND the "Run everything" button so
# both stay in lock-step. The worker enforces ordering via api_jobs.depends_on (SETUP_PREREQS),
# so it's correct with any number of workers. One-time cost ~$8-12, ~30-50 min.
SETUP_PIPELINE: list[str] = [
    "audit",             # AI-state audit -> scored answers (everything downstream needs this)
    "site_crawl",        # technical / on-page SEO crawl
    "gap_model",         # the gap analysis (needs the audit)
    "keyword_research",  # SEO target keywords (LLM seed + Serper grounding) for content + plan
    "plan",              # strategy -> improvement tasks (needs the gap model)
    "sync_plan",         # materialize the plan into trackable work orders
    "citation_analyze",  # AI-citation share-of-voice / who AI quotes (needs the audit)
    "benchmark",         # competitor AI share-of-voice
    "local_rank",        # local Google rankings (needs SERPER_API_KEY)
    "ingest_gbp_reviews", # Google rating + reviews snapshot (Serper places)
    "suggest_prompts",   # AI-suggested tracking prompts
    "mentions_scan",     # web mentions + drafted (human-gated) replies
    "discovery",         # outreach targets (journalists / outlets / communities)
    "production_briefs", # content-to-produce briefs
    "report",            # client report LAST, so it reflects audit + gaps + plan + rankings
]


# Onboarding pipeline prerequisites (the full board enqueued together).
SETUP_PREREQS: dict[str, list[str]] = {
    "gap_model": ["audit"],
    "keyword_research": ["site_crawl", "gap_model"],
    "plan": ["gap_model"],
    "sync_plan": ["plan"],
    "citation_analyze": ["audit"],
    "production_briefs": ["plan"],
    # the client report runs after everything that feeds it
    "report": ["audit", "site_crawl", "gap_model", "keyword_research", "plan", "sync_plan",
               "citation_analyze", "benchmark", "local_rank", "ingest_gbp_reviews",
               "suggest_prompts", "mentions_scan", "discovery", "production_briefs"],
}


# Ad-hoc trigger cascade: trigger X -> also enqueue these children, each waiting on its
# parent. Keeps "Regenerate plan" producing tasks + content, and a fresh audit refreshing
# the gap model / plan / citations. Edges chosen to match what an owner expects from one
# click; the depends_on chain + dedup keep it safe and ordered.
TRIGGER_DOWNSTREAM: dict[str, list[str]] = {
    "audit": ["gap_model", "citation_analyze"],
    "gap_model": ["plan", "keyword_research"],
    "plan": ["sync_plan"],
    "sync_plan": ["production_briefs"],
}


def enqueue_pipeline(business_id: int, requested_by: Optional[int] = None) -> list[dict]:
    """Enqueue the full ``SETUP_PIPELINE`` in dependency order, wiring each job's
    ``depends_on`` from ``SETUP_PREREQS`` so ordering holds with any number of workers.
    Shared by the onboarding wizard and the "Run everything" button. Returns a list of
    ``{job_type, job_id, already_running, error?}`` describing what was queued."""
    enqueued: list[dict] = []
    id_by_type: dict[str, int] = {}   # job_type -> enqueued job id, to wire dependencies
    for jt in SETUP_PIPELINE:
        try:
            dep_ids = [id_by_type[d] for d in SETUP_PREREQS.get(jt, []) if d in id_by_type]
            job_id, active = _jobs.enqueue(business_id, jt, requested_by=requested_by,
                                           depends_on=dep_ids or None)
            if job_id:
                id_by_type[jt] = job_id
            enqueued.append({"job_type": jt, "job_id": job_id or active, "already_running": job_id is None})
        except Exception as e:  # a single bad job type must not abort the whole run
            enqueued.append({"job_type": jt, "job_id": None, "error": str(e)[:120]})
    return enqueued


def enqueue_downstream(business_id: int, root_type: str, root_id: int,
                       requested_by: Optional[int] = None) -> list[dict]:
    """Breadth-first enqueue the ``TRIGGER_DOWNSTREAM`` descendants of a just-enqueued root
    job, each ``depends_on`` its parent. ``root_id`` is the api_jobs id of the already-enqueued
    root. Returns a list of ``{job_type, job_id, already_active}`` for the chained jobs so the
    API can report what it kicked off.

    A child that is already active (someone triggered it concurrently) is recorded but NOT
    recursed into — its own downstream chain, if any, was created by whoever enqueued it.
    """
    chained: list[dict] = []
    frontier: list[tuple[str, int]] = [(root_type, root_id)]
    seen: set[str] = {root_type}
    while frontier:
        parent_type, parent_id = frontier.pop(0)
        for child in TRIGGER_DOWNSTREAM.get(parent_type, []):
            if child in seen:
                continue
            seen.add(child)
            cid, cactive = _jobs.enqueue(
                business_id, child, requested_by=requested_by, depends_on=[parent_id]
            )
            chained.append({"job_type": child, "job_id": cid or cactive, "already_active": cid is None})
            if cid is not None:  # only recurse into jobs we actually enqueued
                frontier.append((child, cid))
    return chained
