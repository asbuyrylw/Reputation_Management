"""
Graph 3 -- Multi-channel Content Remediation agent (LangGraph, human-gated).

Orchestrates ABOVE the verified content_generator single-asset loop -- it does NOT
reimplement drafting or the compliance gate. From a root-cause + gap brief it:

  plan a multi-channel BUNDLE -> draft each channel asset (budget-bounded) through
  the seam, run the VERIFIED content_generator._compliance gate, persist to
  content_drafts (pending_review) -> plan internal links among them -> HUMAN GATE
  (LangGraph interrupt) for holistic batch review -> finalize.

The per-asset compliance gate (deterministic + LLM, fail-closed) stays inside
content_generator; this graph adds the fan-out + internal-link plan + a durable
batch interrupt. Nothing is auto-published -- each draft still goes through the
existing per-asset approve() to become an asset.

CLI:  python -m rep_engine.agent_content --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict  # type: ignore

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

try:
    from . import agent_tools as tools
    from . import content_generator as _cg
    from .db import db
except ImportError:  # pragma: no cover -- loose-script fallback
    import agent_tools as tools  # type: ignore
    import content_generator as _cg  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("agent_content")

MAX_ASSETS = int(os.getenv("REMEDIATION_MAX_ASSETS", "6"))
_CHANNELS = {"article", "social_post", "landing_page", "video_script"}

PLAN_SYSTEM = (
    "You are a reputation content strategist. Given a root-cause + gap brief, plan a small, high-impact "
    "multi-channel remediation BUNDLE (<=6 assets) that crowds out the contested narrative with accurate, "
    "OWNED content. Respond with ONE minified JSON object and nothing else: "
    '{"assets":[{"channel":"article|social_post|landing_page|video_script","platform":"(social only: '
    'reddit|x|facebook|linkedin|instagram, else null)","title":"..","topic":"..","keywords":[".."]}]}'
)

DRAFT_SYSTEM = (
    "You are an expert content writer. Draft the requested asset for the given channel: accurate, on-brand, "
    "and optimized to be CITED by AI answer engines (front-load the direct answer; cover the key entities "
    "and questions). For social_post: short and platform-appropriate. For landing_page: a headline plus a "
    "few sections. For video_script: a short spoken script. Never fabricate and never make compliance-risky "
    "claims (guarantees of results, '#1'/'best', 'risk-free'). Output ONLY the asset body as plain text."
)

LINKS_SYSTEM = (
    "Given a set of newly drafted owned assets, propose internal links BETWEEN them (and to obvious owned "
    "hubs) to build topical authority. Respond with ONE minified JSON object and nothing else: "
    '{"links":[{"from_id":<id>,"to_id":<id>,"anchor":".."}]}'
)


class RemState(TypedDict, total=False):
    business_id: int
    business: dict
    brief: dict
    plan: list
    drafts: list
    internal_links: list
    decision: dict


def _brief(business_id: int, biz: dict) -> dict:
    """Build the remediation brief from the latest root_cause (Graph 1) + gap model,
    falling back to the business goal/contested terms if those don't exist yet."""
    brief = {"goal": biz.get("goal"), "contested_terms": biz.get("contested_terms")}
    with db() as conn:
        rc = conn.execute("SELECT model FROM root_cause WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                          (business_id,)).fetchone()
        gm = conn.execute("SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                          (business_id,)).fetchone()
    if rc and rc.get("model"):
        brief["root_cause"] = rc["model"]
    if gm and gm.get("model"):
        brief["gap"] = gm["model"]
    return brief


# ----------------------------------------------------------------------------
# Nodes
# ----------------------------------------------------------------------------
def _node_plan(state: RemState) -> dict:
    try:
        res = tools.llm_json(PLAN_SYSTEM, json.dumps(state.get("brief", {}), default=str),
                             business_id=state["business_id"], tier="mid", operation="remediation_plan")
    except tools.BudgetExceededError:
        return {"plan": []}
    assets = res.get("assets") if isinstance(res, dict) else None
    plan = [a for a in (assets or []) if isinstance(a, dict) and a.get("channel") in _CHANNELS]
    return {"plan": plan[:MAX_ASSETS]}


def _node_draft(state: RemState) -> dict:
    biz = state["business"]
    drafts = []
    for a in state.get("plan", [])[:MAX_ASSETS]:
        if tools.over_budget(state["business_id"]):
            break
        try:
            body = tools.llm_text(
                DRAFT_SYSTEM,
                json.dumps({"business": biz.get("name"), "goal": biz.get("goal"),
                            "channel": a.get("channel"), "platform": a.get("platform"),
                            "title": a.get("title"), "topic": a.get("topic"),
                            "keywords": a.get("keywords")}),
                business_id=state["business_id"], tier="mid", max_tokens=1500,
                operation="remediation_draft")
        except tools.BudgetExceededError:
            break
        if not body:
            continue
        comp = _cg._compliance(body)               # the VERIFIED deterministic+LLM gate
        status = "needs_fix" if comp.get("pass") is False else "pending_review"
        with db() as conn:
            row = conn.execute(
                "INSERT INTO content_drafts (business_id, asset_type, title, body, compliance_pass, "
                "compliance_flags, status) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (state["business_id"], a.get("channel"), a.get("title"), body, comp.get("pass"),
                 json.dumps(comp.get("flags", [])), status)).fetchone()
            conn.commit()
        drafts.append({"id": row["id"], "channel": a.get("channel"), "title": a.get("title"),
                       "compliance_pass": comp.get("pass"), "status": status})
    return {"drafts": drafts}


def _node_internal_links(state: RemState) -> dict:
    drafts = state.get("drafts", [])
    if len(drafts) < 2:
        return {"internal_links": []}
    try:
        res = tools.llm_json(
            LINKS_SYSTEM,
            json.dumps({"assets": [{"id": d["id"], "title": d["title"], "channel": d["channel"]}
                                   for d in drafts]}),
            business_id=state["business_id"], tier="mid", operation="remediation_links")
    except tools.BudgetExceededError:
        return {"internal_links": []}
    return {"internal_links": res.get("links", []) if isinstance(res, dict) else []}


def _node_gate(state: RemState) -> dict:
    drafts = state.get("drafts") or []
    decision = interrupt({
        "drafts": drafts,
        "internal_links": state.get("internal_links"),
        # drafts where the LLM screen was unavailable (deterministic rules still ran);
        # flag them so the batch reviewer knows they were not machine-screened.
        "not_machine_screened": [d["id"] for d in drafts if d.get("compliance_pass") is None],
        "instructions": "Review the bundle. Reply with {'approved': true|false}. Compliant drafts then "
                        "publish individually via content_generator.approve; nothing auto-publishes.",
    })
    return {"decision": decision if isinstance(decision, dict) else {"approved": False}}


def _node_finalize(state: RemState) -> dict:
    # The per-asset publish gate is unchanged -- drafts stay pending_review for the
    # existing approve() path. Record only the holistic batch decision in state.
    return {}


def _edge_after_plan(state: RemState) -> str:
    # empty plan (e.g. over budget) -> finish without an empty human-gate pause.
    return "draft" if state.get("plan") else "finalize"


def _edge_after_draft(state: RemState) -> str:
    return "internal_links" if state.get("drafts") else "gate"


def build_graph(checkpointer=None):
    g = StateGraph(RemState)
    g.add_node("plan", _node_plan)
    g.add_node("draft", _node_draft)
    g.add_node("internal_links", _node_internal_links)
    g.add_node("gate", _node_gate)
    g.add_node("finalize", _node_finalize)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", _edge_after_plan, {"draft": "draft", "finalize": "finalize"})
    g.add_conditional_edges("draft", _edge_after_draft,
                            {"internal_links": "internal_links", "gate": "gate"})
    g.add_edge("internal_links", "gate")
    g.add_edge("gate", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


def _checkpointer():
    """Shared checkpointer (durable PostgresSaver when AGENT_CHECKPOINT_PG is set,
    else in-memory). See agent_tools.make_checkpointer."""
    return tools.make_checkpointer()


def remediate(business_id: int, *, checkpointer=None) -> dict:
    """Plan + draft a multi-channel remediation bundle and pause at the human gate."""
    _cg._ensure_table()
    with db() as conn:
        b = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not b:
            raise SystemExit(f"No business id {business_id}")
    biz = {k: b[k] for k in ("name", "domain", "goal", "contested_terms", "services", "geo")}
    app = build_graph(checkpointer or _checkpointer())
    cfg = {"configurable": {"thread_id": f"remediation-{business_id}"}}
    # idempotency: never clobber a bundle already paused at the human gate (would
    # duplicate content_drafts and silently lose the in-flight review). Same guard
    # class as agent_incident. (Cross-process needs a PostgresSaver; see _checkpointer.)
    snap = app.get_state(cfg)
    if getattr(snap, "next", None):
        vals = getattr(snap, "values", None) or {}
        return {"drafts": vals.get("drafts", []), "internal_links": vals.get("internal_links", []),
                "status": "pending_human_review", "duplicate": True,
                "thread_id": cfg["configurable"]["thread_id"]}
    out = app.invoke({"business_id": business_id, "business": biz,
                      "brief": _brief(business_id, biz), "plan": [], "drafts": [],
                      "internal_links": []}, config=cfg)
    return {"drafts": out.get("drafts", []), "internal_links": out.get("internal_links", []),
            "status": "pending_human_review" if "__interrupt__" in out else "done",
            "thread_id": cfg["configurable"]["thread_id"]}


def resume(business_id: int, decision: dict, *, checkpointer=None) -> dict:
    """Resume a paused remediation bundle with the human decision."""
    app = build_graph(checkpointer or _checkpointer())
    cfg = {"configurable": {"thread_id": f"remediation-{business_id}"}}
    snap = app.get_state(cfg)
    if not getattr(snap, "next", None):
        raise SystemExit("No paused remediation bundle to resume for this business.")
    app.invoke(Command(resume=decision), config=cfg)
    return {"business_id": business_id, "decision": decision}


def main() -> None:
    ap = argparse.ArgumentParser(description="Multi-channel Content Remediation agent (Graph 3)")
    ap.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(remediate(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
