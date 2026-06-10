"""
Reputation Crowding-Out Engine -- Anthropic Message Batches (50%-off scoring)
===========================================================================
The audit scoring pass (one orchestrator JSON call per answer) is embarrassingly
parallel and latency-tolerant -- audits are periodic -- so it is an ideal Batch
API candidate: the Message Batches API gives a flat 50% discount on all token
usage and completes within ~1h.

`score_run_batched(business_id)` re-scores a finished run's non-failed answers in
ONE batch instead of N synchronous calls, validating each result through the same
ScoreResult schema and the same untrusted-content fencing as the live path, then
writing the metrics back. It is ADDITIVE -- it does not touch the verified
audit() loop -- so you can adopt the cheaper batch scoring without risking the
synchronous default.

This is a thin client over the existing resilient http layer (no SDK). Live
submission needs ANTHROPIC_API_KEY; request building and result parsing are
unit-tested with the http layer (and batch run) mocked.

CLI:
    python -m rep_engine.batch score --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Optional

from pydantic import ValidationError

try:
    from . import ai_state_audit as a
    from . import http
    from .db import db
    from .llm_schemas import ScoreResult
except ImportError:  # pragma: no cover -- allows running as a loose script
    import ai_state_audit as a  # type: ignore
    import http  # type: ignore
    from db import db  # type: ignore
    from llm_schemas import ScoreResult  # type: ignore

log = logging.getLogger("batch")

ANTHROPIC_BASE = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")


def _headers() -> dict:
    return {"x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"}


# ----------------------------------------------------------------------------
# Thin Message Batches client
# ----------------------------------------------------------------------------
def submit(requests: list[dict], *, timeout: int = 60) -> Optional[str]:
    """Create a batch from [{custom_id, params}] requests. Returns the batch id
    or None on failure."""
    res = http.request_json("POST", f"{ANTHROPIC_BASE}/v1/messages/batches",
                            headers=_headers(), json={"requests": requests}, timeout=timeout)
    if res.failed:
        log.warning("batch submit failed: %s", res.error)
        return None
    return (res.data or {}).get("id")


def poll(batch_id: str, *, timeout: int = 30) -> dict:
    """Return the batch object (or {} on failure). `processing_status` is 'ended'
    when results are ready; `results_url` points at the JSONL output."""
    res = http.request_json("GET", f"{ANTHROPIC_BASE}/v1/messages/batches/{batch_id}",
                            headers=_headers(), timeout=timeout)
    return (res.data or {}) if not res.failed else {}


def results(batch_id: str, *, timeout: int = 120) -> dict:
    """Fetch and parse the JSONL results into {custom_id: result_dict}."""
    url = poll(batch_id).get("results_url")
    if not url:
        return {}
    res = http.request_json("GET", url, headers=_headers(), parse_json=False, timeout=timeout)
    if res.failed or not res.text:
        return {}
    out: dict = {}
    for line in res.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        cid = rec.get("custom_id")
        if cid:
            out[cid] = rec.get("result", {})
    return out


def run(requests: list[dict], *, poll_interval: float = 5.0, max_wait: float = 3600.0) -> dict:
    """Submit, poll to completion, and return {custom_id: result}. Blocks up to
    max_wait seconds. Returns {} if submission fails or the wait times out."""
    bid = submit(requests)
    if not bid:
        return {}
    waited = 0.0
    while waited < max_wait:
        if poll(bid).get("processing_status") == "ended":
            return results(bid)
        time.sleep(poll_interval)
        waited += poll_interval
    log.warning("batch %s did not finish within %.0fs", bid, max_wait)
    return {}


# ----------------------------------------------------------------------------
# Scoring integration (additive -- does not touch audit())
# ----------------------------------------------------------------------------
def build_score_requests(b: dict, answers: list[dict]) -> list[dict]:
    """One batch request per answer (custom_id = 'ans-{id}'), reusing the audit
    SCORING_SYSTEM and the SAME untrusted-content fencing as the synchronous
    score_answer path."""
    model, _ = a._model_for("cheap")
    reqs = []
    for ans in answers:
        user = json.dumps({
            "business": b["name"], "goal": b.get("goal"),
            "contested_terms": a._split(b.get("contested_terms")),
            "prompt": ans.get("prompt", ""),
            "answer": a._fence_untrusted(ans.get("answer_text", "")),
            "cited_sources": a._fence_untrusted(json.dumps(ans.get("cited_sources", []), default=str)),
        })
        reqs.append({
            "custom_id": f"ans-{ans['id']}",
            "params": {
                "model": model, "max_tokens": 2000,
                "system": a.SCORING_SYSTEM + " Respond with a single minified JSON object and nothing else.",
                "messages": [{"role": "user", "content": user}],
            },
        })
    return reqs


def _extract_score(result) -> Optional[dict]:
    """Pull the scoring dict out of a batch result and validate it through
    ScoreResult. Returns None for errored/garbled results (treated as unscored)."""
    if not isinstance(result, dict) or result.get("type") != "succeeded":
        return None
    msg = result.get("message", {}) or {}
    text = "".join(blk.get("text", "") for blk in msg.get("content", []) if blk.get("type") == "text")
    parsed = a._parse_json_lenient(text)
    if not parsed:
        return None
    try:
        return ScoreResult.model_validate(parsed).model_dump()
    except ValidationError:
        return None


def score_run_batched(business_id: int, run_id: Optional[int] = None) -> int:
    """Score (or re-score) a finished run's non-failed answers in ONE Anthropic
    batch (50% off vs the synchronous per-answer pass), validating each result and
    writing the metrics back. Returns the number of rows updated. Requires a live
    ANTHROPIC_API_KEY for submission; additive (does not touch audit())."""
    with db() as conn:
        b = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not b:
            return 0
        if run_id is None:
            r = conn.execute(
                "SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
            run_id = r["id"] if r else None
        if not run_id:
            return 0
        answers = conn.execute(
            "SELECT id, prompt, answer_text, cited_sources FROM answers "
            "WHERE run_id=%s AND NOT COALESCE(failed, false)", (run_id,)).fetchall()
    if not answers:
        return 0

    out = run(build_score_requests(dict(b), [dict(x) for x in answers]))

    updated = 0
    with db() as conn:
        for ans in answers:
            score = _extract_score(out.get(f"ans-{ans['id']}"))
            if score is None:
                continue
            conn.execute(
                "UPDATE answers SET sentiment=%s, goal_alignment=%s, mentions_contested=%s, "
                "surfaces_owned=%s WHERE id=%s",
                (score.get("sentiment"), score.get("goal_alignment"),
                 bool(score.get("mentions_contested")), bool(score.get("surfaces_owned")),
                 ans["id"]))
            updated += 1
        conn.commit()
    log.info("batch-scored %d/%d answers for run %s", updated, len(answers), run_id)
    return updated


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch-score a run via the Anthropic Message Batches API")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score", help="batch-score a finished run's answers")
    sc.add_argument("--business-id", type=int, required=True)
    sc.add_argument("--run-id", type=int, default=None)
    args = ap.parse_args()
    if args.cmd == "score":
        n = score_run_batched(args.business_id, args.run_id)
        print(f"Updated {n} answer(s) with batch scores.")


if __name__ == "__main__":
    main()
