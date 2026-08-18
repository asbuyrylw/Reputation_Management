"""
Reputation Crowding-Out Engine -- Orchestrator
==============================================
One command runs the full pipeline for a business:
  intake -> AI-state audit -> site crawl -> gap model -> strategy plan -> report

This is the end-to-end entrypoint. Individual modules can still be run alone
(see each module's __main__), but this wires them in the correct order and
shares one Postgres database via the REP_DB_DSN env var.

Usage:
    # one-shot for a brand-new business
    python -m rep_engine.orchestrator run \
        --name "Team Unstoppable" --domain teamunstoppable.com \
        --services "life insurance, retirement, debt elimination" \
        --goal "Dominate local Cincinnati branded queries with accurate narrative" \
        --contested "MLM,pyramid scheme,scam" --geo "Cincinnati OH" \
        --start 2026-06-09 --max-pages 40

    # re-run monthly cycle for an existing business (audit -> gap -> report)
    python -m rep_engine.orchestrator cycle --business-id 1
"""

from __future__ import annotations

import argparse
import logging
import os


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

from . import ai_state_audit as m1
from . import strategy_generator as m2
from . import site_crawl as m3
from . import report_generator as m4
from . import tracking as m5
from . import content_generator as m6
from . import timeline_estimator as m7
from . import acceleration_advisor as m8
from . import feedback_loop as m9
from . import citation_analytics as m10
from . import runstate as m_rs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("orchestrator")


# ----------------------------------------------------------------------------
# Optional LangGraph agentic steps -- OFF by default so the verified cycle's cost
# and behavior are unchanged; opt in per-graph via env. Agent modules are imported
# lazily (the orchestrator stays importable without langgraph) and a graph failure
# can never break the core cycle.
# ----------------------------------------------------------------------------
def _agent_enabled(flag: str) -> bool:
    return os.getenv(flag, "").lower() in ("1", "true", "yes")


def _safe_agentic(label: str, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 -- an optional agent must never break the cycle
        log.warning("agentic step %s skipped: %s", label, e)
        return {"skipped": str(e)}


def _maybe_agentic_steps(rs, bid: int) -> None:
    """Append the opt-in agentic graphs as cycle steps (each gated by its own env
    flag). Graphs 1/2/4 are read-only/queue-only; Graph 3 drafts a bundle that still
    requires the existing per-asset human approval -- nothing is auto-published."""
    if (_agent_enabled("AGENT_INCIDENT_IN_CYCLE") or _agent_enabled("AGENT_REMEDIATION_IN_CYCLE")) \
            and not _agent_enabled("AGENT_CHECKPOINT_PG"):
        log.warning("In-cycle incident/remediation enabled WITHOUT AGENT_CHECKPOINT_PG: human-gate "
                    "interrupts use an in-memory checkpointer and won't be resumable after this "
                    "process exits. Set AGENT_CHECKPOINT_PG=1 for durable cross-process review.")
    if _agent_enabled("AGENT_ROOTCAUSE_IN_CYCLE"):
        def _run():
            from . import agent_rootcause as a
            return a.investigate(bid)
        rs.step("root_cause", lambda: _safe_agentic("root_cause", _run),
                "CYCLE root-cause / source-intelligence (Graph 1)")
    if _agent_enabled("AGENT_DISCOVERY_IN_CYCLE"):
        def _run():
            from . import agent_discovery as a
            return a.discover(bid)
        rs.step("discovery", lambda: _safe_agentic("discovery", _run),
                "CYCLE discovery of outreach targets (Graph 2)")
    if _agent_enabled("AGENT_INCIDENT_IN_CYCLE"):
        def _run():
            from . import agent_incident as a
            return a.scan(bid)
        rs.step("incident_scan", lambda: _safe_agentic("incident_scan", _run),
                "CYCLE reactive-incident scan (Graph 4)")
    if _agent_enabled("AGENT_REMEDIATION_IN_CYCLE"):
        def _run():
            from . import agent_content as a
            return a.remediate(bid)
        rs.step("remediation", lambda: _safe_agentic("remediation", _run),
                "CYCLE multi-channel content remediation (Graph 3)")
    if _agent_enabled("AGENT_PRODUCTION_BRIEFS_IN_CYCLE"):
        def _run():
            from . import production_brief as a
            return a.plan(bid)
        rs.step("production_briefs", lambda: _safe_agentic("production_briefs", _run),
                "CYCLE video/social production briefs (off-platform specs)")
    if _agent_enabled("AGENT_RICH_MEDIA_IN_CYCLE"):
        def _run():
            from . import rich_media_generator as a
            from .config import settings
            s = settings()
            types = (
                [t.strip() for t in s.rich_media_types.split(",") if t.strip()]
                if s.rich_media_types else None
            )
            return a.generate(bid, types)
        rs.step("rich_media", lambda: _safe_agentic("rich_media", _run),
                "CYCLE rich-media drafts (podcast, slides, infographic, articles via NotebookLM)")





def _add_business(args) -> int:
    m1.init_db()
    with db() as conn:
        row = conn.execute(
            """INSERT INTO businesses (name, domain, services, profile, goal,
                contested_terms, geo) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (args.name, args.domain, args.services, getattr(args, "profile", None),
             args.goal, args.contested, args.geo),
        ).fetchone()
        conn.commit()
    log.info("Created business id=%d", row["id"])
    return row["id"]


def _maybe_batch_score(rs, bid: int) -> None:
    """When AUDIT_BATCH_SCORING is on, the audit deferred scoring; fill the metrics now via
    the Anthropic Batch API (50% off). Must run BEFORE gap_model (which reads the scores)."""
    if m1._batch_scoring():
        from . import batch as m_batch
        rs.step("batch_score", lambda: m_batch.score_run_batched(bid), "batch-score answers (50% off)")


def run_full(args) -> None:
    bid = _add_business(args)
    rs = m_rs.RunState.start(bid, kind="run", resume=getattr(args, "resume", False))
    rs.step("audit", lambda: m1.audit(bid), "STEP audit — AI-state audit")
    _maybe_batch_score(rs, bid)
    rs.step("site_crawl", lambda: m3.crawl_cmd(bid, args.max_pages), "STEP site crawl")
    rs.step("gap_model", lambda: m1.build_gap_model(bid), "STEP gap model")
    rs.step("remerge", lambda: _remerge(bid), "STEP re-merge site findings")
    rs.step("plan", lambda: m2.plan_cmd(bid, args.start), "STEP strategy plan")
    rs.step("sync_tracking", lambda: m5.sync_plan(bid), "STEP sync work orders")
    if getattr(args, "generate_drafts", False):
        rs.step("generate_drafts", lambda: m6.generate(bid), "STEP generate content drafts (pending review)")
    _maybe_agentic_steps(rs, bid)
    rs.step("report", lambda: m4.generate(bid), "STEP client report")
    rs.finish()
    log.info("DONE. Business id=%d fully processed.", bid)


def _remerge(bid: int) -> None:
    """Site crawl runs before gap_model in run_full ordering, so re-apply the
    site summary onto the freshly-built gap model."""
    with db() as conn:
        sa = conn.execute(
            "SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (bid,),
        ).fetchone()
    if sa:
        summary = sa["summary"] if isinstance(sa["summary"], dict) else __import__("json").loads(sa["summary"])
        m3.merge_into_gap_inputs(bid, summary)


def run_cycle(args) -> None:
    """Monthly re-run for an existing business. Resumable: a failed/interrupted
    cycle can be re-invoked with --resume to skip already-completed steps."""
    bid = args.business_id
    rs = m_rs.RunState.start(bid, kind="cycle", resume=getattr(args, "resume", False))
    rs.step("audit", lambda: m1.audit(bid), "CYCLE audit")
    _maybe_batch_score(rs, bid)
    rs.step("gap_model", lambda: m1.build_gap_model(bid), "CYCLE gap model")
    rs.step("attribution", lambda: m5.attribute(bid), "CYCLE attribution")
    rs.step("alert", lambda: m5.check_alert(bid), "CYCLE alert check")
    rs.step("citation", lambda: m10.analyze(bid, quiet=True), "CYCLE citation analytics")
    rs.step("learn", lambda: m9.learn(bid, quiet=True), "CYCLE learn from outcomes")
    rs.step("timeline", lambda: m7.estimate(bid, quiet=True), "CYCLE timeline estimate")
    rs.step("accelerate", lambda: m8.advise(bid, quiet=True), "CYCLE acceleration options")
    _maybe_agentic_steps(rs, bid)
    rs.step("report", lambda: m4.generate(bid), "CYCLE report")
    rs.finish()
    log.info("Cycle complete for business id=%d", bid)


def main() -> None:
    ap = argparse.ArgumentParser(description="Reputation engine orchestrator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="full pipeline for a new business")
    pr.add_argument("--name", required=True)
    pr.add_argument("--domain", required=True)
    pr.add_argument("--services")
    pr.add_argument("--profile")
    pr.add_argument("--goal")
    pr.add_argument("--contested", help="comma-separated terms to OUT-COMPETE (not suppress)")
    pr.add_argument("--geo")
    pr.add_argument("--start", help="ISO date the plan begins (default today)")
    pr.add_argument("--max-pages", type=int, default=40)
    pr.add_argument("--generate-drafts", action="store_true",
                    help="also auto-draft content for generatable work orders (pending human review)")
    pr.add_argument("--resume", action="store_true",
                    help="resume the latest unfinished run for this business, skipping completed steps")

    pc = sub.add_parser("cycle", help="monthly re-run for an existing business")
    pc.add_argument("--business-id", type=int, required=True)
    pc.add_argument("--resume", action="store_true",
                    help="resume the latest unfinished cycle, skipping completed steps")

    args = ap.parse_args()
    if args.cmd == "run":
        run_full(args)
    elif args.cmd == "cycle":
        run_cycle(args)


if __name__ == "__main__":
    main()
