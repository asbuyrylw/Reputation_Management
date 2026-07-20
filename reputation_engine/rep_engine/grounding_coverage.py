"""
Grounding-coverage ADVISORY (warning-only)
==========================================
Answers ONE question for a generation topic: does the client's VERIFIED source corpus actually hold
facts for it? -- and surfaces the answer as a WARNING, never a gate. Content generation is never
blocked, skipped, or held by this signal; a draft is always produced. The advisory is pure metadata
that rides on the draft (quality_notes["coverage_advisory"]) and, at the plan level, on strategy_view,
so the owner can see "this piece was written without supporting facts -- add source material" and act,
without the engine ever refusing to generate.

Design invariants (why this can never stop production or crash a job):
  * SIGNAL SOURCE is grounding_retrieval.retrieve ONLY -- it catches every exception and returns []
    on both a dormant schema and a real broken read; it NEVER raises. HARD RULE: this module must
    NOT call any source_material.* function (corpus/grounding_block/guardrails/has_material/...):
    those are fail-LOUD re-raisers and would crash generate_for_wo / generate_batch.
  * coverage() is a TOTAL function -- its whole body is wrapped so ANY surprise degrades to
    status="unknown" (which the UI renders as nothing), never an exception into the caller.
  * The value is never read by any gate, revise loop, status transition, or return-None path.

Same retrieval path + rank floor the writer uses, so "grounded here" == "the writer's retrieve()
surfaces >= 1 fact above the floor" -- the draft flag and the plan flag can't drift.
"""
from __future__ import annotations

import logging
import os

try:
    from . import grounding_retrieval as _gr
except ImportError:  # pragma: no cover -- direct-run fallback
    import grounding_retrieval as _gr  # type: ignore

log = logging.getLogger("grounding.coverage")

# A topic needs at least this many matched docs AND a best rank at/above the soft floor to count as
# solidly "grounded"; below that (but > 0 matches) it is "thin". Env-overridable for tuning. The soft
# floor sits ABOVE grounding_retrieval.MIN_GROUNDING_RANK (0.02) -- a match that barely clears the
# retrieval floor is "thin", not "grounded".
SOLID_DOCS = int(os.getenv("COVERAGE_SOLID_DOCS", "2"))
SOFT_RANK = float(os.getenv("GROUNDING_SOFT_RANK", "0.05"))

_UNGROUNDED_NOTE = (
    "No source material covers this topic yet, so this draft was written without your verified facts "
    "— it may read generic or contain placeholders. Add your website or documents in Content → Source "
    "Material to ground it.")
_THIN_NOTE = (
    "Only limited source material matched this topic, so parts of this draft may be under-grounded. "
    "Add more source material in Content → Source Material to strengthen it.")


def scope_query(wo: dict) -> str:
    """The canonical topic string a work order is generated/grounded against: batch pieces set
    target_query; plan work orders fall back to their gap query, then the title. ONE definition so a
    draft and its plan advisory key off the identical string (mirrors content_generator._scope_q)."""
    wo = wo or {}
    return (wo.get("target_query")
            or (wo.get("gap_specifics") or {}).get("source_query")
            or wo.get("title") or "")


def _unknown(topic: str) -> dict:
    return {"topic": topic or "", "grounded": None, "matched_docs": 0, "rank": 0.0,
            "entity_risk": False, "status": "unknown", "note": None}


def coverage(business_id: int, topic: str, *, entity_risk=None) -> dict:
    """WARN-only grounding coverage for a topic. TOTAL function: never raises, always returns a dict.

    status: "ungrounded" (corpus reachable, nothing matches) | "thin" (1 weak match) |
            "grounded" (>= SOLID_DOCS matches, best rank >= SOFT_RANK) | "unknown" (blank topic or an
            unexpected read failure -- rendered as nothing, never a false "ungrounded").

    entity_risk is accepted (a caller may pass a precomputed per-business bool) but NEVER computed
    here -- computing it would require challenge_profile, which can SystemExit; that is deferred.
    """
    topic = (topic or "").strip()
    if not topic:
        return _unknown(topic)   # no identifiable topic -> can't assess (not "ungrounded")
    try:
        docs = _gr.retrieve(business_id, topic, limit=6)   # fail-SAFE: [] on dormant OR broken read
        matched = len(docs)
        best = round(float(docs[0].get("rank") or 0.0), 4) if docs else 0.0
        if matched == 0:
            status, note = "ungrounded", _UNGROUNDED_NOTE
        elif matched < SOLID_DOCS or best < SOFT_RANK:
            status, note = "thin", _THIN_NOTE
        else:
            status, note = "grounded", None
        return {"topic": topic, "grounded": status == "grounded", "matched_docs": matched,
                "rank": best, "entity_risk": bool(entity_risk), "status": status, "note": note}
    except Exception as e:  # noqa: BLE001 -- advisory must NEVER propagate into the generation job
        log.debug("coverage() degraded to unknown for business %s topic %r: %s", business_id, topic, e)
        return _unknown(topic)


def plan_coverage(signals: list) -> dict:
    """Roll up already-computed per-topic coverage() signals into ONE plan-level advisory. Pure: it
    recomputes nothing, so the plan count is a true aggregate of the exact per-piece signals the
    drafts carry (no drift). status: "gap" (any ungrounded) > "thin" (any thin) > "ok"; "unknown"
    when there are no topics or every signal is unknown."""
    sigs = [s for s in (signals or []) if isinstance(s, dict)]
    total = len(sigs)
    grounded = sum(1 for s in sigs if s.get("status") == "grounded")
    thin = sum(1 for s in sigs if s.get("status") == "thin")
    ungrounded = sum(1 for s in sigs if s.get("status") == "ungrounded")
    unknown = sum(1 for s in sigs if s.get("status") == "unknown")
    ungrounded_topics = [s.get("topic") for s in sigs if s.get("status") == "ungrounded" and s.get("topic")][:10]
    if total == 0 or unknown == total:
        status, reason = "unknown", None
    elif ungrounded > 0:
        status = "gap"
        reason = (f"{ungrounded} of {total} planned pieces have no source material for their topic. "
                  "Add website pages or documents in Content → Source Material so they're written from "
                  "your real facts.")
    elif thin > 0:
        status = "thin"
        reason = (f"{thin} of {total} planned pieces have only thin source material. Add more in "
                  "Content → Source Material to strengthen them.")
    else:
        status, reason = "ok", None
    return {"status": status, "total_topics": total, "grounded": grounded, "thin": thin,
            "ungrounded": ungrounded, "unknown": unknown,
            "ungrounded_topics": ungrounded_topics, "reason": reason}
