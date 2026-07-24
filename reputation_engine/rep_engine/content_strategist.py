"""
Content Strategist (Phase 1) -- the planning brain between the gap model and work-order creation.
=================================================================================================
The engine MEASURES gaps well (build_gap_model) but historically ACTED on them with a deterministic
template: exactly one work order per gap item, capability + week hardcoded, the AI score / severity /
priority_order all ignored. The result was a thin, generic ~20-slot plan while the real multi-piece
content spread only appeared later, at generation time, in a *separate* module (content_batch) -- so
the strategy page could never SHOW the program it would produce. That is the strategy<->content
disconnect this module closes.

`plan(business_id, gap, ...)` is an LLM planning pass -- bounded exactly like the gap model (JSON
schema + deterministic guards) and business-agnostic (reads business_profile.for_business so finance
is just one bucket) -- that turns the gap model + keyword intent + topic clusters + org profile +
existing inventory into ONE prioritized content PROGRAM: a ranked list of cluster CAMPAIGNS, each a
pillar + N clusters (+ a comparison page for commercial intent) with intent/funnel tags, an
atomization spec, and a per-piece cadence slot. strategy_generator.build_work_orders then materializes
those campaigns (instead of the old 1-per-gap loops), so the plan is deep and content becomes an
EXECUTION of the plan, not a parallel engine.

Cost posture (owner decision): PLANNING IS BRIEFS-ONLY -> cheap. This module never drafts content; it
emits titles + one-line briefs + structure. Generation stays just-in-time downstream (Phase 3). One
Sonnet-tier call (+ optional deterministic guards); ledgered + budget-guarded like the gap model.

Fail-safe: any LLM failure / empty output -> plan() returns {} and the caller (plan_cmd) falls back
to the existing deterministic template, so a strategist outage never breaks planning.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Optional

try:
    from .db import db
    from . import ai_state_audit as _audit
    from . import business_profile as _bp
    from . import topical_authority as _ta
    from . import cost
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import ai_state_audit as _audit  # type: ignore
    import business_profile as _bp  # type: ignore
    import topical_authority as _ta  # type: ignore
    import cost  # type: ignore

log = logging.getLogger("content_strategist")

# One planning call, Sonnet-tier by default (same tier the gap model synthesis uses): strong at
# structured strategy, ~5x cheaper than Opus, and no Opus-4.8 prose-before-JSON truncation. All
# env-overridable for ops without a code change.
STRATEGIST_TIER = os.getenv("STRATEGIST_TIER", _audit.GAP_MODEL_TIER)
STRATEGIST_TIMEOUT = int(os.getenv("STRATEGIST_TIMEOUT", "480"))
STRATEGIST_DEADLINE = int(os.getenv("STRATEGIST_DEADLINE", "900"))
STRATEGIST_MAX_TOKENS = int(os.getenv("STRATEGIST_MAX_TOKENS", "12000"))


def _enabled() -> bool:
    return os.getenv("CONTENT_STRATEGIST_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


# Bounds -- the strategist NEVER trusts the LLM alone. Research backbone: 8-12 clusters per pillar is
# the topical-authority sweet spot (5-page activation min, 15-article authority threshold); we clamp
# to a ceiling so a hallucinated 40-cluster campaign can't blow up the plan/cost, and cap total
# planned pieces + campaigns so the year-plan stays sane.
_MAX_CAMPAIGNS = int(os.getenv("STRATEGIST_MAX_CAMPAIGNS", "10"))
_MAX_CLUSTERS = int(os.getenv("STRATEGIST_MAX_CLUSTERS", "12"))
_MAX_TOTAL_PIECES = int(os.getenv("STRATEGIST_MAX_PIECES", "150"))

# Cadence (Phase 2): front-loaded cluster BURSTS then a governed DRIP -- the research-backed pattern
# (dump the foundational network fast, then steady ~2/week so content posts out gradually over a
# year). Every knob env-overridable. A new domain drips slower (spam-safety / indexation headroom).
_BURST_WEEKS = int(os.getenv("STRATEGIST_BURST_WEEKS", "6"))            # the initial-dump window
_BURST_PER_CAMPAIGN = int(os.getenv("STRATEGIST_BURST_PER_CAMPAIGN", "4"))  # pillar + first clusters
_DRIP_PER_WEEK = int(os.getenv("STRATEGIST_DRIP_PER_WEEK", "2"))        # steady-state pace after the burst
_HORIZON_WEEKS = int(os.getenv("STRATEGIST_HORIZON_WEEKS", "52"))       # a full year of runway

# Video plan (Phase 5): plan a VIDEO option for each campaign's pillar + top N clusters. Each is a
# ready-to-produce plan (generate -> script + SRT captions + VideoObject schema; render -> MP4 on
# demand), so video is a big per-campaign part of the mix -- the owner picks which to actually make.
_VIDEO_CLUSTERS = int(os.getenv("STRATEGIST_VIDEO_CLUSTERS", "3"))

# Business-value weight by search intent (commercial/transactional convert; informational builds the
# top of funnel). Drives severity ranking so the plan leads with the highest-leverage campaigns.
_INTENT_WEIGHT = {"commercial": 3, "transactional": 3, "investigational": 3,
                  "local": 2, "navigational": 2, "informational": 1, "unknown": 1}

_STOP = {"the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "best", "near", "me",
         "top", "how", "what", "is", "are", "with", "your", "you", "my", "do", "does", "vs",
         "why", "who", "page", "overview"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2 and t not in _STOP}


_SYSTEM_BASE = (
    "You are an ELITE content strategist for an AI-reputation program. Your job: read a business's "
    "AI-visibility GAP MODEL (what ChatGPT / Perplexity / Gemini / Google AI Overviews get wrong or "
    "miss about it), its keyword INTENT data, its topic CLUSTERS, and its EXISTING content, then "
    "design ONE prioritized content PROGRAM that will close those gaps and get the business cited by "
    "answer engines. You do NOT write the content -- you plan it (titles + one-line briefs + "
    "structure). Return STRICT JSON only.\n"
    "MODEL THE WORK AS CLUSTER CAMPAIGNS, NOT PAGES. Each weak topic becomes a CAMPAIGN = 1 PILLAR "
    "page (a definitive, comprehensive overview) + 6-12 CLUSTER pages (each answers ONE specific "
    "sub-question / long-tail query, FAQ-style) + (only when the intent is commercial) 1 COMPARISON "
    "or 'best <thing> in <place>' page. This pillar+cluster structure is what builds topical "
    "authority and gets cited. Err toward MORE coverage, not less -- a topic with 8-12 interlinked "
    "pages outranks a single long guide.\n"
    "Return JSON: {summary (string), campaigns (array of {"
    "topic (string, the pillar theme), "
    "intent (one of: informational|commercial|transactional|local), "
    "funnel_stage (one of: awareness|consideration|decision), "
    "why (string -- the SPECIFIC gap / weak AI answer this campaign closes), "
    "gap_source (short string naming the gap origin, e.g. 'missing owned content', 'competitor "
    "analysis', 'topical authority', 'keyword intent'), "
    "target_queries (array of the exact weak AI questions / keywords this campaign answers -- pull "
    "these VERBATIM from weak_queries[].prompt, competitor_defense[].query, and the keyword lists), "
    "priority (integer 1..N, 1 = highest leverage), "
    "pillar ({title, content_type ('article'), why}), "
    "clusters (array of 6-12 {title, content_type (one of 'blog'|'faq'|'article'), "
    "intent, target_query (the specific question/keyword this piece answers), why}), "
    "comparison_page ({title} or null), "
    "atomization ({social_posts (int 4-12), video_script (bool), infographic (bool), email (bool)})"
    "})}.\n"
    "RULES: (1) Ground EVERY campaign in a real gap-model signal -- do not invent topics the gap "
    "model / keywords don't support. (2) Do NOT propose a page whose title IS a contested accusation "
    "(that reinforces the negative); for a contested frame, plan a legitimacy / transparency / "
    "third-party-corroboration asset that answers the concern factually. (3) Do NOT duplicate a topic "
    "the business ALREADY has strong owned content for (see already_have). (4) Cover a MIX of intents "
    "across campaigns (informational pillars feed commercial comparison pages feed decision pages) -- "
    "do not produce only informational. (5) Apply AEO/GEO best practice in every brief: answer-first "
    "(a 40-60 word direct answer up top), FAQ/Q&A blocks, one quotable statistic per section, "
    "explicit entity naming (business + location + service), and a schema type per intent (FAQPage / "
    "Article / Product). (6) 3-8 campaigns is typical; go deep on the few highest-leverage gaps "
    "rather than one shallow campaign per gap. JSON only."
)


def _system_prompt(profile: dict) -> str:
    """Per-tenant strategist system prompt: splice in the business's license/sensitive-ID policy
    (finance suppresses specific credential numbers; generic gets none), the positive-only
    self-distinction policy, and the untrusted-content instruction -- mirroring _gap_system so the
    strategist inherits the SAME compliance guardrails as the gap model. Business-agnostic."""
    try:
        lic = _bp.license_policy_for(profile or {})
    except Exception:  # noqa: BLE001 -- profile read must never break the prompt
        lic = ""
    reg_fin = bool((profile or {}).get("regulated_financial"))
    fin_note = ""
    if reg_fin:
        fin_note = (" This is a regulated-finance business: keep every brief compliant -- no "
                    "performance guarantees, no specific license/credential numbers, legitimacy via "
                    "general licensing statements + third-party corroboration, and require any "
                    "disclosures the profile lists.")
    return _SYSTEM_BASE + fin_note + lic + _audit.NO_NEGATIVE_DISAMBIGUATION_POLICY + _audit.UNTRUSTED_INSTRUCTION


def _existing_titles(business_id: int, limit: int = 40) -> list[str]:
    """A compact list of what the business ALREADY has (approved drafts + assets) so the strategist
    doesn't re-plan covered topics. Fail-safe -> []."""
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT title FROM content_drafts WHERE business_id=%s AND status IN "
                "('approved','published') UNION SELECT title FROM assets WHERE business_id=%s",
                (business_id, business_id)).fetchall()
        return [r["title"] for r in rows if r.get("title")][:limit]
    except Exception:  # noqa: BLE001 -- no table yet / read error -> nothing known owned
        return []


def _signals(business_id: int) -> dict:
    """Keyword-intent + topic-cluster signals the strategist folds into the plan (the data the old
    planner computed for DISPLAY only and never turned into content). Each fail-safe -> empty."""
    by_intent: list = []
    clusters: list = []
    try:
        by_intent = (_ta.by_intent(business_id) or {}).get("by_intent") or []
    except Exception as e:  # noqa: BLE001
        log.warning("strategist: by_intent unavailable (%s)", e)
    try:
        clusters = (_ta.clusters(business_id) or {}).get("clusters") or []
    except Exception as e:  # noqa: BLE001
        log.warning("strategist: clusters unavailable (%s)", e)
    # Trim to the highest-leverage slices so the payload stays small (planning is cheap). Include the
    # real DEMAND (search volume) + difficulty per intent/cluster so the strategist prioritizes by
    # opportunity, not just bucket size (was dropped entirely before).
    return {
        "keyword_intents": [{"intent": g.get("intent"), "keywords": g.get("keywords"),
                             "examples": g.get("examples"), "needs_content": g.get("needs_content"),
                             "total_search_volume": g.get("total_search_volume"),
                             "avg_difficulty": g.get("avg_difficulty")}
                            for g in by_intent[:8]],
        "topic_clusters": [{"topic": c.get("topic"), "spokes": (c.get("spokes") or [])[:8],
                            "needs_content": c.get("needs_content"),
                            "keyword_count": c.get("keyword_count"),
                            "total_search_volume": c.get("total_search_volume")}
                           for c in clusters[:12]],
    }


# ----------------------------------------------------------------------------
# Deterministic post-processing: severity ranking + cadence -- never left to the LLM.
# ----------------------------------------------------------------------------
def _campaign_severity(camp: dict, gap: dict, demand_by_intent: Optional[dict] = None) -> float:
    """Rank a campaign by SoV-gap x DEMAND x business-value, computed in CODE (not trusted to the
    LLM): how many weak AI answers it covers (the crux of the visibility gap) x how much its intent
    converts x the real search demand for that intent, plus a bonus for the LLM's own priority hint.
    Higher = attack first."""
    tqs: set[str] = set()
    for q in (camp.get("target_queries") or []):
        tqs |= _tokens(q)
    tqs |= _tokens((camp.get("pillar") or {}).get("title", ""))
    for cl in (camp.get("clusters") or []):
        tqs |= _tokens(cl.get("target_query") or cl.get("title") or "")
    # weak AI answers this campaign plausibly fixes (token overlap on the weak query prompt)
    covers = 0
    for w in (gap.get("weak_queries") or []):
        wt = _tokens(w.get("prompt") or "") | _tokens(w.get("addressed_by") or "")
        if wt and len(tqs & wt) >= 2:
            covers += 1
    intent_w = _INTENT_WEIGHT.get((camp.get("intent") or "unknown").lower(), 1)
    try:
        llm_pri = int(camp.get("priority") or 99)
    except (TypeError, ValueError):
        llm_pri = 99
    pri_bonus = max(0, 6 - llm_pri)  # LLM priority 1 -> +5, 6+ -> 0
    # real search demand for this campaign's intent (log-scaled, capped +3) so high-volume gaps lead
    demand = (demand_by_intent or {}).get((camp.get("intent") or "").lower(), 0) or 0
    demand_bonus = min(3.0, math.log10(demand + 1)) if demand > 0 else 0.0
    return covers * 2.0 + intent_w + pri_bonus * 0.5 + demand_bonus


def _flatten_pieces(camp: dict, rank: int) -> list[dict]:
    """Turn one ranked campaign into an ordered list of content PIECES (pillar, clusters, comparison)
    with a per-piece cadence WEEK (basic burst-then-drip for Phase 1; Phase 2 extends to a full
    52-week calendar). Higher-ranked campaigns roll out earlier (the 'initial dump' front-load), then
    a campaign's clusters drip ~2/week after its pillar."""
    intent = (camp.get("intent") or "informational").lower()
    is_local = intent == "local"
    cap = "local_content_creation" if is_local else "content_writing"
    pieces: list[dict] = []
    base = 2 + rank                       # pillars of top campaigns lead (wk 2, 3, 4, ...)
    pillar = camp.get("pillar") or {}
    p_title = pillar.get("title") or camp.get("topic") or "Pillar page"
    pieces.append({"title": p_title, "capability": cap, "role": "pillar", "week": base,
                   "content_type": pillar.get("content_type") or "article",
                   "target_query": camp.get("topic") or p_title,
                   "why": pillar.get("why") or camp.get("why") or ""})
    # clusters drip after the pillar, ~2 per week
    for i, cl in enumerate((camp.get("clusters") or [])[:_MAX_CLUSTERS]):
        title = cl.get("title")
        if not title:
            continue
        pieces.append({"title": title,
                       "capability": "local_content_creation" if (cl.get("intent") or intent).lower() == "local" else "content_writing",
                       "role": "cluster", "week": base + 1 + (i // 2),
                       "content_type": cl.get("content_type") or "blog",
                       "target_query": cl.get("target_query") or title,
                       "why": cl.get("why") or ""})
    comp = camp.get("comparison_page")
    if isinstance(comp, dict) and comp.get("title"):
        pieces.append({"title": comp["title"], "capability": "content_writing", "role": "comparison",
                       "week": base + 2, "content_type": "article",
                       "target_query": comp["title"], "why": "Wins commercial / comparison queries."})
    return pieces


def _assign_cadence(campaigns: list[dict], *, new_domain: bool = False) -> None:
    """Spread every campaign piece across a real BURST-then-DRIP calendar (mutates piece['week']).
    Weeks 1..BURST_WEEKS front-load each campaign's pillar + first clusters (campaigns staggered so
    the initial dump touches several topics fast); the remainder drips ~DRIP_PER_WEEK per week,
    round-robin across campaigns, out to the horizon -- so content posts out gradually, not all at
    once. week -> target_date downstream, so the calendar shows the rollout with no FE change."""
    drip = max(1, _DRIP_PER_WEEK - (1 if new_domain else 0))
    # BURST: pillar + first clusters of each campaign inside the front-load window.
    for ci, camp in enumerate(campaigns):
        start = min(_BURST_WEEKS, 1 + ci)                       # stagger campaign starts (wk1, wk2, ...)
        for j, pc in enumerate((camp.get("pieces") or [])[:_BURST_PER_CAMPAIGN]):
            pc["week"] = min(_BURST_WEEKS, start + (j // 2))    # ~2 pieces/week within the burst
            pc["_placed"] = True
    # DRIP: everything else, interleaved across campaigns so each drip week touches multiple topics.
    queues = [[pc for pc in (c.get("pieces") or []) if not pc.get("_placed")] for c in campaigns]
    ordered: list[dict] = []
    while any(queues):
        for q in queues:
            if q:
                ordered.append(q.pop(0))
    for k, pc in enumerate(ordered):
        pc["week"] = min(_HORIZON_WEEKS, _BURST_WEEKS + 1 + (k // drip))
    for camp in campaigns:
        for pc in (camp.get("pieces") or []):
            pc.pop("_placed", None)


def _add_video_plan(campaigns: list[dict]) -> None:
    """Plan a VIDEO option for each campaign's pillar + top clusters (Phase 5). Generating one yields
    a script + SRT captions + VideoObject schema (content_quality); rendering an MP4 (HeyGen/Veo) is a
    separate on-demand click. Opt-in (on_click=True) so a LOT of video options surface without being
    auto-drafted -- the owner picks which to produce. Each video inherits its source piece's cadence
    week so it sits beside its article."""
    for camp in campaigns:
        pieces = camp.get("pieces") or []
        pillar = next((p for p in pieces if p.get("role") == "pillar"), None)
        clusters = [p for p in pieces if p.get("role") == "cluster"][:_VIDEO_CLUSTERS]
        vids = []
        for src in ([pillar] if pillar else []) + clusters:
            vids.append({
                "title": f"Video: {src['title']}", "capability": "explainer_video", "role": "video",
                "week": src.get("week", 3), "content_type": "video_script",
                "target_query": src.get("target_query") or src["title"],
                "why": (f"Explainer video of '{src['title']}' — generate the script + captions + "
                        f"VideoObject schema, then render an MP4 on demand."),
                "on_click": True,
            })
        pieces.extend(vids)
        camp["pieces"] = pieces


def _postprocess(model: dict, gap: dict, *, new_domain: bool = False,
                 demand_by_intent: Optional[dict] = None) -> dict:
    """Deterministic guards + enrichment over the raw LLM plan: clamp counts, rank campaigns by
    severity (SoV-gap x value), assign each campaign a stable id + cadence-weeked pieces, and cap
    total pieces. Returns the finished ContentStrategy the planner materializes."""
    campaigns = model.get("campaigns")
    if not isinstance(campaigns, list) or not campaigns:
        return {}
    campaigns = [c for c in campaigns if isinstance(c, dict) and (c.get("pillar") or c.get("topic"))][:_MAX_CAMPAIGNS]
    # rank by computed severity (desc), stable on ties
    for c in campaigns:
        c["_severity"] = _campaign_severity(c, gap, demand_by_intent)
    campaigns.sort(key=lambda c: -c["_severity"])
    out: list[dict] = []
    total = 0
    for rank, c in enumerate(campaigns):
        cid = f"C{rank + 1:02d}"
        pieces = _flatten_pieces(c, rank)
        if not pieces:
            continue
        if total + len(pieces) > _MAX_TOTAL_PIECES:
            pieces = pieces[: max(0, _MAX_TOTAL_PIECES - total)]
        if not pieces:
            break
        total += len(pieces)
        out.append({
            "id": cid,
            "topic": c.get("topic") or (c.get("pillar") or {}).get("title"),
            "intent": (c.get("intent") or "informational").lower(),
            "funnel_stage": (c.get("funnel_stage") or "awareness").lower(),
            "why": c.get("why") or "",
            "gap_source": (c.get("gap_source") or "content strategy").strip().lower(),
            "target_queries": c.get("target_queries") or [],
            "priority_rank": rank,
            "severity": round(c["_severity"], 2),
            "atomization": c.get("atomization") if isinstance(c.get("atomization"), dict) else {},
            "pieces": pieces,
        })
    if not out:
        return {}
    # Assign the real burst-then-drip cadence across ALL campaigns (mutates each piece's week ->
    # target_date downstream), so a year of content posts out gradually instead of clumping. A new
    # domain (little/no published inventory) drips slower for indexation safety.
    _assign_cadence(out, new_domain=new_domain)
    # Plan per-campaign video options (pillar + top clusters) AFTER cadence, so videos inherit their
    # source's week and don't perturb the drip.
    _add_video_plan(out)
    # Stable per-piece ordinal within its campaign -> a churn-proof work-order key across monthly
    # re-plans (the LLM rewords target queries/titles every run; keying the board on those churns it).
    for camp in out:
        for i, pc in enumerate(camp.get("pieces") or []):
            pc["ordinal"] = i
    total_pieces = sum(len(c["pieces"]) for c in out)
    video_count = sum(1 for c in out for p in c["pieces"] if p.get("role") == "video")
    return {"summary": model.get("summary", ""), "campaigns": out,
            "counts": {"campaigns": len(out), "pieces": total_pieces, "content": total,
                       "videos": video_count},
            "cadence": {"burst_weeks": _BURST_WEEKS, "drip_per_week": _DRIP_PER_WEEK,
                        "horizon_weeks": _HORIZON_WEEKS,
                        "last_week": max((pc["week"] for c in out for pc in c["pieces"]), default=0)}}


def plan(business_id: int, gap: dict, *, business: Optional[dict] = None,
         profile: Optional[dict] = None) -> dict:
    """Design the content PROGRAM for a business from its gap model + keyword/cluster signals +
    profile. Returns a ContentStrategy {summary, campaigns:[{id, topic, intent, funnel_stage, why,
    gap_source, target_queries, priority_rank, pieces:[{title, capability, role, week, ...}]}], counts}
    or {} on any failure / when disabled (caller falls back to the deterministic template).

    Cheap: ONE Sonnet-tier planning call, briefs-only (no drafting). Ledgered + budget-guarded like
    the gap model."""
    if not _enabled():
        return {}
    if not isinstance(gap, dict) or not gap.get("summary"):
        return {}
    # Budget guard: skip the (small) planning call when the tenant is already over its monthly cap,
    # and fall back to the deterministic template -- mirrors the gap-model guard so we never spend
    # past the ceiling. Planning is cheap, but the cap is the runaway backstop.
    try:
        if cost.over_budget(business_id):
            log.warning("strategist: business %s over monthly budget; skipping LLM plan (fallback to "
                        "template).", business_id)
            return {}
    except Exception:  # noqa: BLE001 -- a cost read must never break planning
        pass
    if profile is None:
        try:
            profile = _bp.for_business(business_id)
        except Exception:  # noqa: BLE001
            profile = {}
    biz = business or {}
    _existing = _existing_titles(business_id)
    _sig = _signals(business_id)
    payload = json.dumps({
        "business": {k: biz.get(k) for k in ("name", "domain", "services", "goal", "geo",
                                             "industry", "contested_terms")},
        "gap_summary": gap.get("summary"),
        "weak_queries": (gap.get("weak_queries") or [])[:20],
        "missing_owned_content": (gap.get("missing_owned_content") or [])[:20],
        "competitor_defense": (gap.get("competitor_defense") or [])[:12],
        "local_seo_gaps": (gap.get("local_seo_gaps") or [])[:10],
        "priority_order": (gap.get("priority_order") or [])[:20],
        "audience_priorities": (gap.get("audience_priorities") or [])[:6],
        "signals": _sig,
        "already_have": _existing,
        "content_type_mix": (profile or {}).get("default_content_types"),
        "social_channels": (profile or {}).get("social_channels"),
        "has_local_presence": (profile or {}).get("has_local_presence", True),
    }, default=str)
    system = _system_prompt(profile or {})
    try:
        model = _audit.orchestrator_json(
            system, payload, tier=STRATEGIST_TIER, max_tokens=STRATEGIST_MAX_TOKENS,
            timeout=STRATEGIST_TIMEOUT, deadline=STRATEGIST_DEADLINE)
    except Exception as e:  # noqa: BLE001 -- an LLM failure must never break planning
        log.warning("strategist: LLM plan failed (%s); falling back to template.", e)
        return {}
    # Ledger the planning spend (estimate-based, like the gap model) so it counts against COGS + cap.
    try:
        _sm, _ = _audit._model_for(STRATEGIST_TIER) if _audit.ORCHESTRATOR == "anthropic" else (None, None)
        if _sm is None:
            _, _sm = _audit._model_for(STRATEGIST_TIER)
        cost.record(business_id, None, _audit.ORCHESTRATOR, "content_strategist", _sm,
                    cost.approx_tokens(system + payload),
                    cost.approx_tokens(json.dumps(model, default=str) if isinstance(model, dict) else ""))
    except Exception:  # noqa: BLE001 -- cost logging must never break planning
        pass
    if not isinstance(model, dict) or not model.get("campaigns"):
        log.warning("strategist: empty/invalid plan for business %s; falling back to template.", business_id)
        return {}
    # new_domain drips slower (indexation-safety): a business with almost no published inventory is
    # treated as new, so the cadence front-loads less aggressively. Proxy = few existing pieces.
    # demand_by_intent feeds real search volume into campaign severity so high-demand gaps lead.
    _demand = {(g.get("intent") or "").lower(): int(g.get("total_search_volume") or 0)
               for g in _sig.get("keyword_intents", [])}
    strategy = _postprocess(model, gap, new_domain=(len(_existing) < 3), demand_by_intent=_demand)
    if strategy.get("campaigns"):
        log.info("strategist: business %s -> %d campaigns, %d pieces",
                 business_id, strategy["counts"]["campaigns"], strategy["counts"]["pieces"])
    return strategy


def latest(business_id: int) -> dict:
    """The most recent persisted ContentStrategy for a business (for strategy_view / re-plan diff).
    Fail-safe -> {}."""
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT strategy FROM content_strategies WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,)).fetchone()
        if not row:
            return {}
        s = row["strategy"]
        return s if isinstance(s, dict) else (json.loads(s) if s else {})
    except Exception:  # noqa: BLE001 -- table may not exist yet
        return {}
