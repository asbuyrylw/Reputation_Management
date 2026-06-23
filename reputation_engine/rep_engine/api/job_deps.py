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


# Onboarding pipeline prerequisites (the full board enqueued together).
SETUP_PREREQS: dict[str, list[str]] = {
    "gap_model": ["audit"],
    "plan": ["gap_model"],
    "sync_plan": ["plan"],
    "citation_analyze": ["audit"],
    "production_briefs": ["plan"],
    # the client report runs after everything that feeds it
    "report": ["audit", "site_crawl", "gap_model", "plan", "sync_plan", "citation_analyze",
               "benchmark", "local_rank", "suggest_prompts", "mentions_scan", "discovery",
               "production_briefs"],
}


# Ad-hoc trigger cascade: trigger X -> also enqueue these children, each waiting on its
# parent. Keeps "Regenerate plan" producing tasks + content, and a fresh audit refreshing
# the gap model / plan / citations. Edges chosen to match what an owner expects from one
# click; the depends_on chain + dedup keep it safe and ordered.
TRIGGER_DOWNSTREAM: dict[str, list[str]] = {
    "audit": ["gap_model", "citation_analyze"],
    "gap_model": ["plan"],
    "plan": ["sync_plan"],
    "sync_plan": ["production_briefs"],
}


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
