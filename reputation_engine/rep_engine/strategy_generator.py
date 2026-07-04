"""
Reputation Crowding-Out Engine -- Module 2: Strategy + Work-Order Generator
===========================================================================
Consumes the structured GAP MODEL from Module 1 (ai_state_audit.py) and produces:
  1. A phased, dated strategic plan (front-loaded fast wins -> build -> amplify -> steady-state).
  2. Concrete WORK ORDERS, each classified as AUTO (system does it) or HUMAN
     (work order for a person/VA), with a recommended TOOL drawn from a registry.
  3. Metrics + monitoring cadence tied back to Module 1's diff().

Tool philosophy
---------------
The TOOL_REGISTRY is an AVAILABLE toolbox, not a mandate. Each capability lists
candidate tools (AppSumo lifetime deals, open-source, and APIs). The generator
picks the best fit by preference order (auto/API > open-source > AppSumo-manual),
and only assigns an AppSumo tool when it genuinely fits the task. If nothing fits,
the work order says so and falls back to the system's own generation or a plain
human instruction. Tools can be enabled/disabled per deployment.

Run:
    python strategy_generator.py plan --business-id 1 --start 2026-06-09
    python strategy_generator.py tools          # list the registry
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("strategy_generator")



# ----------------------------------------------------------------------------
# TOOL REGISTRY  --  available toolbox, picked only when beneficial
# ----------------------------------------------------------------------------
class Exec(str, Enum):
    AUTO = "auto"          # system executes via API/code, no human needed
    SEMI = "semi"          # API exists but needs human review/trigger
    MANUAL = "manual"      # no usable API; human operates the tool from a work order


@dataclass
class Tool:
    key: str
    name: str
    capability: str            # canonical capability id (see CAPABILITIES)
    execution: Exec
    notes: str = ""
    enabled: bool = True        # flip off per deployment if you don't own/want it


# Canonical capabilities the engine can request for a work order.
CAPABILITIES = [
    "site_audit", "keyword_research", "topic_research", "content_writing",
    "content_optimization", "fact_checking", "video_creation", "video_repurpose",
    "social_publishing", "press_outreach", "media_list_building", "link_building",
    "review_generation", "ai_visibility_tracking", "form_capture", "visitor_tracking",
    "schema_markup", "course_microsite",
]

# Registry. preference within a capability = order listed (best/most-automatable first).
# AppSumo lifetime-deal tools are included as MANUAL options where they fit.
TOOL_REGISTRY: list[Tool] = [
    # --- site audit / technical SEO ---
    Tool("lighthouse", "Lighthouse CI", "site_audit", Exec.AUTO, "OSS; programmatic Core Web Vitals + SEO checks. Preferred."),
    Tool("screaming_frog", "Screaming Frog CLI", "site_audit", Exec.AUTO, "Crawl + on-page export via CLI. Preferred for structure."),
    Tool("screpy", "Screpy", "site_audit", Exec.MANUAL, "AppSumo; dashboarded audit. Use for client-facing visuals."),
    Tool("siteguru", "SiteGuru", "site_audit", Exec.MANUAL, "AppSumo; readable audit + to-do list."),
    Tool("brandalyzer", "Brandalyzer", "site_audit", Exec.MANUAL, "AppSumo; brand/site analysis."),
    Tool("clickrank", "ClickRank", "site_audit", Exec.MANUAL, "AppSumo; SEO automation/audit."),
    Tool("vispr_seo", "Vispr SEO Network", "link_building", Exec.MANUAL, "AppSumo; network/SEO."),
    # --- keyword / topic research ---
    Tool("topic_mojo", "Topic Mojo", "topic_research", Exec.MANUAL, "AppSumo; question/topic discovery -- great for matching AI prompt gaps."),
    Tool("writerzen", "WriterZen", "keyword_research", Exec.MANUAL, "AppSumo; keyword + content cluster."),
    Tool("getgeni", "GetGenie", "keyword_research", Exec.SEMI, "AppSumo; some API; SEO + content."),
    Tool("squirrly", "Squirrly SEO", "content_optimization", Exec.MANUAL, "AppSumo; live on-page optimization (WordPress)."),
    # --- content writing / optimization / fact-check ---
    Tool("llm_native", "Engine-native LLM", "content_writing", Exec.AUTO, "System writes drafts directly. Default for owned content."),
    Tool("texta", "Texta.ai", "content_writing", Exec.SEMI, "AppSumo; long-form gen."),
    Tool("shopia", "Shopia.ai", "content_writing", Exec.SEMI, "AppSumo; content + scheduling."),
    Tool("blogify", "Blogify", "content_writing", Exec.MANUAL, "AppSumo; blog gen/repurpose."),
    Tool("katteb", "Katteb", "fact_checking", Exec.MANUAL, "AppSumo; fact-checked content -- useful for trust-sensitive claims."),
    Tool("konvey", "Konvey", "content_optimization", Exec.MANUAL, "AppSumo; conversion copy."),
    # --- video creation / repurpose ---
    Tool("steve_ai", "Steve.ai", "video_creation", Exec.MANUAL, "AppSumo; script->video explainers."),
    Tool("pipio", "Pipio", "video_creation", Exec.MANUAL, "AppSumo; AI presenter video."),
    Tool("vadoo", "Vadoo.tv/.ai", "video_creation", Exec.MANUAL, "AppSumo; short video gen + hosting."),
    Tool("flexclip", "FlexClip", "video_creation", Exec.MANUAL, "AppSumo; quick branded video."),
    Tool("onetake", "OneTake AI", "video_repurpose", Exec.MANUAL, "AppSumo; long->clips."),
    Tool("hippo", "Hippo Video", "video_repurpose", Exec.MANUAL, "AppSumo; video + hosting."),
    Tool("videopeel", "VideoPeel", "review_generation", Exec.MANUAL, "AppSumo; collect video testimonials."),
    Tool("motionvid", "MotionVid AI", "video_creation", Exec.MANUAL, "AppSumo; video gen."),
    # --- social publishing ---
    Tool("creasquare", "CreaSquare", "social_publishing", Exec.SEMI, "AppSumo; multi-channel social gen + schedule."),
    Tool("genius_ai", "Genius.ai", "social_publishing", Exec.SEMI, "AppSumo; social content/ads."),
    # --- press / outreach / media lists ---
    Tool("press_ranger", "Press Ranger", "media_list_building", Exec.SEMI, "AppSumo; ~journalist/outlet DB. Primary for local media lists."),
    Tool("bizreply", "BizReply", "social_publishing", Exec.MANUAL, "AppSumo; monitor + reply to relevant mentions (engagement)."),
    Tool("cxassist", "CXAssist", "press_outreach", Exec.SEMI, "AppSumo; email assistant/auto-reply."),
    # --- link building ---
    Tool("linksy", "Linksy AI Link Builder", "link_building", Exec.MANUAL, "AppSumo; outreach link building."),
    Tool("linkly", "Linkly", "link_building", Exec.SEMI, "AppSumo; trackable links/redirects (analytics, not acquisition)."),
    # --- AI visibility tracking (complements Module 1) ---
    Tool("measuremate", "MeasureMate", "ai_visibility_tracking", Exec.MANUAL, "AppSumo; metrics dashboard."),
    Tool("module1", "Engine Module 1 audit", "ai_visibility_tracking", Exec.AUTO, "Our own harness. Primary tracker."),
    # --- capture / tracking / courses ---
    Tool("deftform", "DeftForm", "form_capture", Exec.SEMI, "AppSumo; forms -> webhook to GHL."),
    Tool("visitortracking", "VisitorTracking.com", "visitor_tracking", Exec.SEMI, "AppSumo; site visitor ID/analytics."),
    Tool("learniverse", "Learniverse", "course_microsite", Exec.MANUAL, "AppSumo; courses (financial-literacy content asset)."),
    Tool("acadle", "Acadle", "course_microsite", Exec.MANUAL, "AppSumo; academy/community (authority asset)."),
    Tool("notebooklm", "NotebookLM", "topic_research", Exec.MANUAL, "Free; synthesize source docs into briefs/audio."),
    Tool("getgeni2", "Vadoo AI captions", "video_repurpose", Exec.MANUAL, "AppSumo; captions/clips."),
]


def registry_for(capability: str) -> list[Tool]:
    pref = {Exec.AUTO: 0, Exec.SEMI: 1, Exec.MANUAL: 2}
    tools = [t for t in TOOL_REGISTRY if t.capability == capability and t.enabled]
    return sorted(tools, key=lambda t: pref[t.execution])


def best_tool(capability: str) -> Optional[Tool]:
    tools = registry_for(capability)
    return tools[0] if tools else None


# ----------------------------------------------------------------------------
# Mapping gap-model sections -> capabilities + phase
# ----------------------------------------------------------------------------
@dataclass
class WorkOrder:
    wo_id: str
    title: str
    capability: str
    execution: str
    recommended_tool: Optional[str]
    alternatives: list[str]
    instruction: str
    phase: str
    week: int
    depends_on: list[str] = field(default_factory=list)
    rationale: dict = field(default_factory=dict)   # B1: {gap_source, why, source}
    why_helps_ai_rep: str = ""                       # C10: how it helps AI reputation
    why_helps_seo: str = ""                          # C10: how it helps local/SEO
    predicted_ai_points: Optional[float] = None      # estimated AI-score points this task adds
    predicted_seo_impact: str = ""                   # qualitative SEO impact: High|Medium|Low
    predicted_basis: str = ""                        # "measured from your results" | "industry baseline"
    area: str = ""                                   # website|blog|outreach|social|local|reviews|tracking
    platform: str = ""                               # for social/local tasks: linkedin|facebook|gbp|...
    gap_specifics: dict = field(default_factory=dict)  # {source_query} -> the weak query/topic this task fixes,
    #                                                    so the UI can link a worst AI answer straight to its task


# Plain-English "how this helps" by capability, so EVERY task shows its why (C10).
_WHY_AI = {
    "content_writing": "Publishes accurate, ownable content AI assistants can cite about you.",
    "schema_markup": "Helps AI engines cleanly extract and trust your facts.",
    "review_generation": "More genuine reviews shift the sentiment AI sees about you.",
    "press_outreach": "Third-party coverage corroborates your narrative from outside your site.",
    "media_list_building": "Builds the outreach list that earns corroborating coverage.",
    "social_publishing": "Adds accurate owned presence for AI to surface instead of the negatives.",
    "local_content_creation": "Geo-specific content AI can cite for local questions about you.",
    "link_building": "Editorial citations raise how often AI surfaces and trusts your sources.",
    "ai_visibility_tracking": "Measures what AI says so you can see the plan working.",
}
_WHY_SEO = {
    "content_writing": "An owned page that can rank for the target search.",
    "schema_markup": "Rich-result eligibility + clearer relevance signals to Google.",
    "review_generation": "Reviews lift your Google Business Profile and map-pack rank.",
    "press_outreach": "Earned links + brand mentions raise domain authority.",
    "media_list_building": "Feeds the earned-link/PR pipeline that lifts rankings.",
    "social_publishing": "Brand signals + a complete GBP help your local rank.",
    "local_content_creation": "A geo landing page to break onto page 1 locally.",
    "link_building": "Backlinks raise domain authority and rankings.",
    "ai_visibility_tracking": "",
}

# Predicted IMPACT: map each capability to the acceleration lever whose effectiveness predicts
# how much one task of this type moves the AI-reputation score. The per-unit gain comes from the
# business's LEARNED weights when available (refines over time), else the industry baseline.
_CAPABILITY_TO_LEVER = {
    "content_writing": "third_party_articles",
    "local_content_creation": "third_party_articles",
    "video_creation": "videos",
    "press_outreach": "earned_press",
    "media_list_building": "earned_press",
    "link_building": "earned_links",
    "review_generation": "reviews",
    "social_publishing": "third_party_articles",
    "gbp_optimization": "reviews",
    # structural / tracking tasks have no direct per-unit score lever
    "schema_markup": None,
    "ai_visibility_tracking": None,
}
# Qualitative SEO impact (point prediction for local rank isn't reliable yet, so we keep it honest).
_CAPABILITY_SEO = {
    "local_content_creation": "High", "gbp_optimization": "High", "link_building": "High",
    "schema_markup": "Medium", "content_writing": "Medium", "review_generation": "Medium",
    "press_outreach": "Medium", "video_creation": "Medium",
    "social_publishing": "Low", "media_list_building": "Low", "ai_visibility_tracking": "—",
}

# Effort weight per capability (1 = quick, 3 = heavy lift) for ROI ranking (item 5D). ROI =
# impact x confidence / effort, so a high-impact, high-confidence, low-effort task ranks first.
_EFFORT = {
    "schema_markup": 1, "ai_visibility_tracking": 1, "social_publishing": 1, "gbp_optimization": 1,
    "review_generation": 2, "content_writing": 2, "local_content_creation": 2, "media_list_building": 2,
    "video_creation": 3, "press_outreach": 3, "link_building": 3,
}
# AEO/GEO content checklist appended to every content-creation task so the writer (human or LLM)
# produces content engines actually CITE, not just SEO filler.
_AEO_CHECKLIST = (
    " AEO/GEO checklist: lead with a 40-60 word direct answer to the target question (front-load); "
    "add an FAQ/Q&A block with FAQPage schema; include one quotable stat or definitive sentence per "
    "section; name the business + city + service explicitly; add a visible last-updated date; match "
    "the page title to the literal user question; add internal links to related owned pages."
)

_CONF_FACTOR = {"high": 1.0, "medium": 0.7, "low": 0.4}
# Points-equivalent for a structural/SEO-only task that has no per-unit AI-score lever, so it can
# still be ROI-ranked against scored tasks.
_SEO_POINTS = {"High": 15.0, "Medium": 8.0, "Low": 3.0, "—": 0.0}

# The AREA a task belongs to, so the plan groups by website / blog / outreach / social / local /
# reviews instead of a flat capability list. surface_actions override this per platform.
_CAPABILITY_AREA = {
    "content_writing": "content", "video_creation": "content",
    "schema_markup": "website", "link_building": "website",
    "press_outreach": "outreach", "media_list_building": "outreach",
    "social_publishing": "social",
    "review_generation": "reviews",
    "local_content_creation": "local", "gbp_optimization": "local",
    "ai_visibility_tracking": "tracking",
}


def predict_impact(business_id: int, capability: str) -> dict:
    """Estimate one task's impact: predicted AI-score points (from learned-or-baseline lever
    effectiveness) + a qualitative SEO impact. Honest about basis + confidence; best used to RANK
    tasks by return, and snapshotted so we can later compare predicted vs measured."""
    lever = _CAPABILITY_TO_LEVER.get(capability)
    ai_points = None
    basis = ""
    confidence = "low"
    if lever:
        try:
            from . import feedback_loop as _fb, acceleration_advisor as _acc
        except ImportError:  # pragma: no cover
            import feedback_loop as _fb  # type: ignore
            import acceleration_advisor as _acc  # type: ignore
        learned = {}
        try:
            learned = _fb.learned_lever_weights(business_id) or {}
        except Exception:  # noqa: BLE001 -- prediction must never break planning
            learned = {}
        if lever in learned and learned[lever] > 0:
            gain = learned[lever]
            basis, confidence = "measured from your results", "medium"
        else:
            gain = (_acc.LEVERS.get(lever, {}) or {}).get("weight", 0.0)
            basis, confidence = "industry baseline", "low"
        ai_points = round(gain * 100.0, 1)  # 0-1 alignment gain per unit -> 0-100 score points
    seo_impact = _CAPABILITY_SEO.get(capability, "—")
    # ROI = expected impact x confidence / effort. Use the AI-score points when a lever exists,
    # else the SEO points-equivalent, so structural tasks rank fairly against scored ones.
    effort = _EFFORT.get(capability, 2)
    impact_pts = ai_points if ai_points is not None else _SEO_POINTS.get(seo_impact, 0.0)
    roi_score = round((impact_pts * _CONF_FACTOR.get(confidence, 0.5)) / max(1, effort), 2)
    return {"ai_points": ai_points, "ai_confidence": confidence, "seo_impact": seo_impact,
            "basis": basis, "effort": effort, "roi_score": roi_score}


PHASES = [
    ("Phase 0 - Baseline & Fast Wins", 0, 2),     # weeks 0-2
    ("Phase 1 - Owned Hub & Schema", 2, 6),       # weeks 2-6
    ("Phase 2 - Corroboration & Amplify", 4, 12), # weeks 4-12
    ("Phase 3 - Steady State & Monitor", 12, 24), # weeks 12+
]


def _phase_for_week(week: int) -> str:
    for name, lo, hi in PHASES:
        if lo <= week < hi:
            return name
    return PHASES[-1][0]


def build_work_orders(gap: dict, business=None) -> list[WorkOrder]:
    wos: list[WorkOrder] = []
    n = 0
    # Media/press angles must reflect THIS business's geo + industry, never a hardcoded example.
    biz = business or {}
    geo = (biz.get("geo") or "").strip() or "your local area"
    industry = (biz.get("industry") or "").strip() or "local-business"

    def add(title, capability, instruction, week, deps=None, *, gap_source="baseline setup", why="",
            source="audited gap", area=None, platform="", source_query=""):
        # Foundational Phase-0 tasks (AI-visibility baseline, GBP claim, review sequence) legitimately
        # trace to no single gap, so they default to gap_source='baseline setup' -> the console shows
        # "From: baseline setup" instead of a blank "why". Gap-derived add() calls pass gap_source
        # explicitly and override this default (audit report Low-19).
        nonlocal n
        n += 1
        tool = best_tool(capability)
        alts = [t.name for t in registry_for(capability)[1:4]]
        wos.append(WorkOrder(
            wo_id=f"WO-{n:03d}", title=title, capability=capability,
            execution=(tool.execution.value if tool else "manual"),
            recommended_tool=(tool.name if tool else None),
            alternatives=alts,
            instruction=instruction, phase=_phase_for_week(week), week=week,
            depends_on=deps or [],
            rationale={"gap_source": gap_source, "why": why, "source": source},
            why_helps_ai_rep=_WHY_AI.get(capability, ""),
            why_helps_seo=_WHY_SEO.get(capability, ""),
            area=area or _CAPABILITY_AREA.get(capability, "other"),
            platform=platform,
            # source_query is the topic/query string the LLM also names in weak_queries[].addressed_by,
            # so a worst answer can be linked to the exact task that fixes it.
            gap_specifics={"source_query": source_query} if source_query else {},
        ))

    # --- Phase 0: fast wins (reviews, tracking baseline, one explainer) ---
    add("Establish AI-visibility baseline", "ai_visibility_tracking",
        "Run Module 1 audit + gap model; store as the baseline report the client receives.", 0)
    add("Launch review-generation sequence", "review_generation",
        "Build a GHL automation texting/emailing happy clients a direct Google review link "
        "post-positive-interaction. Seed reviews mentioning service + locale.", 0)
    add("Claim/optimize Google Business Profile", "social_publishing",
        "Verify GBP; complete categories, services, photos, NAP consistency; enable reviews.", 1,
        area="local", platform="gbp")

    # --- Phase 1: owned content for each missing topic + schema ---
    for i, item in enumerate(gap.get("missing_owned_content", []) or []):
        topic = item.get("topic", f"topic {i+1}")
        atype = item.get("asset_type", "article")
        why = item.get("why", "")
        cap = "video_creation" if "video" in atype.lower() else "content_writing"
        add(f"Create owned asset: {topic}", cap,
            f"Produce a {atype} on '{topic}'. Rationale: {why}. Draft via engine-native LLM; "
            f"fact-check trust-sensitive claims; publish on the business domain.{_AEO_CHECKLIST}", 3,
            gap_source="audited gap: missing owned content", why=why, source_query=topic)
    for sg in gap.get("schema_gaps", []) or []:
        add(f"Add schema: {sg}", "schema_markup",
            f"Generate and deploy JSON-LD ({sg}) on the relevant pages so answer engines "
            f"can cleanly extract facts.", 4, gap_source="audited gap: schema", source_query=str(sg))

    # --- Phase 2: corroboration (press, media list, partner, link) ---
    if gap.get("thin_corroboration"):
        add("Build local media list", "media_list_building",
            f"Assemble a {geo} {industry} journalist + local-outlet list, with pitch angles drawn "
            f"from this business's real differentiators and community involvement (what makes it "
            f"credible and locally newsworthy).", 5,
            gap_source="audited gap: thin corroboration", source_query="local media list")
        for i, claim in enumerate(gap.get("thin_corroboration", [])):
            c = claim.get("claim", f"claim {i+1}")
            where = claim.get("where_to_get_it", "")
            add(f"Corroborate: {c}", "press_outreach",
                f"Secure third-party coverage/mention supporting '{c}'. Source: {where}. "
                f"Draft pitch; route via outreach tool; human approves before send.", 6,
                gap_source="audited gap: thin corroboration", why=c, source_query=c)
    add(f"Book relevant podcast appearances ({industry})", "press_outreach",
        f"Identify 3-5 relevant {geo} / {industry} podcasts; pitch the principal as guest; "
        f"each episode yields an indexed third-party positive page.", 7,
        gap_source="audited gap: thin corroboration", source_query="podcast appearances")

    # --- Per-surface actions straight from the gap model (ethical, accurate only) ---
    # Each surface becomes a PER-PLATFORM task tagged with its area + platform so the plan breaks
    # down by platform (linkedin / facebook / ... ) and local (GBP), not a single social bucket.
    surfaces = gap.get("surface_actions", {}) or {}
    surface_week = {"google_business": 1, "gbp": 1, "linkedin": 5, "facebook": 5, "instagram": 6,
                    "x": 6, "youtube": 7, "tiktok": 8, "pinterest": 9, "threads": 8, "reddit": 8}
    # google_business is the local Google profile, not a social feed -> area=local
    _SURFACE_AREA = {"google_business": "local", "gbp": "local"}
    _SURFACE_PLATFORM = {"google_business": "gbp"}
    for surface, actions in surfaces.items():
        for act in (actions or []):
            wk = surface_week.get(surface, 6)
            platform = _SURFACE_PLATFORM.get(surface, surface)
            area = _SURFACE_AREA.get(surface, "social")
            note = ""
            if surface == "reddit":
                note = (" NOTE: Reddit must be genuine, human, value-add participation only "
                        "-- never automated reputation posting (ban risk + policy violation).")
            add(f"Improve {surface.replace('_', ' ').title()} presence", "social_publishing",
                f"{act}{note}", wk,
                gap_source=f"recommended social presence ({surface})", why="",
                source="recommendation", area=area, platform=platform)

    # --- Local-SEO gaps -> tasks (from first-party SERP reads, via the gap model) ---
    for i, g in enumerate(gap.get("local_seo_gaps", []) or []):
        q = g.get("query", f"local query {i + 1}")
        rec = g.get("recommendation", "Create geo-specific content + strengthen GBP / local citations.")
        add(f"Reach page 1 for '{q}'", "local_content_creation",
            f"{rec} Current position: {g.get('current_rank', 'off page 1')}.", 4,
            gap_source="local search ranking", why=g.get("why", ""), source_query=q)

    # --- Competitor-defense gaps -> tasks (questions a rival wins and you don't) ---
    for i, g in enumerate(gap.get("competitor_defense", []) or []):
        q = g.get("query", f"query {i + 1}")
        rec = g.get("recommendation", "Publish accurate owned content that answers this question well.")
        add(f"Compete for '{q}'", "content_writing",
            f"{rec} A competitor ({g.get('competitor', 'a rival')}) appears here and you don't.", 4,
            gap_source="competitor analysis", why=g.get("why", ""), source_query=q)

    # --- Site-technical gaps -> tasks (thin/missing pages, schema, weak coverage) ---
    for i, g in enumerate(gap.get("site_technical_gaps", []) or []):
        issue = g.get("issue", f"site issue {i + 1}")
        rec = g.get("recommendation", "Fix the on-site issue so AI engines can extract your facts.")
        scap = "schema_markup" if "schema" in f"{issue} {rec}".lower() else "content_writing"
        add(f"Fix site: {issue}", scap, rec, 3,
            gap_source="site crawl", why=g.get("why", ""))

    # --- Phase 3: steady-state monitoring ---
    add("Recurring AI-visibility monitor", "ai_visibility_tracking",
        "Schedule monthly Module 1 audit + diff; generate the monthly progress report.", 12)
    return wos


# ----------------------------------------------------------------------------
# Plan assembly (dates, metrics)
# ----------------------------------------------------------------------------
METRICS = [
    "Avg goal_alignment across answer engines (target: rising; from Module 1 diff)",
    "Contested-term mention rate (target: falling as accurate content crowds out)",
    "Owned-content surfacing rate (target: rising)",
    "# of owned hub pages published with schema",
    "# of third-party corroborating placements (press, podcast, partner)",
    "Google Business review count + average rating + recency",
    "Local branded-query presence in Perplexity / ChatGPT-search",
]


def assemble_plan(business: dict, gap: dict, start: date) -> dict:
    wos = build_work_orders(gap, business)
    bid = business.get("id")
    for w in wos:
        w_start = start + timedelta(weeks=w.week)
        # start = the planned start; target_date = the due/end date (~2 weeks to act on it).
        w.__dict__["start_date"] = w_start.isoformat()
        w.__dict__["target_date"] = (w_start + timedelta(weeks=2)).isoformat()
        if bid is not None:
            imp = predict_impact(bid, w.capability)
            w.predicted_ai_points = imp["ai_points"]
            w.predicted_seo_impact = imp["seo_impact"]
            w.predicted_basis = imp["basis"]
            # ROI score in the persisted rationale (no new column) so the task board can rank by it.
            w.rationale = {**(w.rationale or {}), "roi_score": imp["roi_score"], "effort": imp["effort"]}
    # Item 5D: order the plan so the highest-ROI work leads WITHIN each phase (phases keep their
    # week sequencing; within a phase, best return first). Stable sort preserves prior order on ties.
    _phase_rank = {name: i for i, (name, _lo, _hi) in enumerate(PHASES)}
    wos.sort(key=lambda w: (_phase_rank.get(w.phase, 99),
                            -float((w.rationale or {}).get("roi_score") or 0)))
    phases = {}
    for name, lo, hi in PHASES:
        phases[name] = {
            "weeks": f"{lo}-{hi if hi < 24 else '24+'}",
            "work_orders": [w.wo_id for w in wos if w.phase == name],
        }
    auto = [w for w in wos if w.execution == "auto"]
    human = [w for w in wos if w.execution in ("manual", "semi")]
    # Silent-success guard: build_work_orders always emits baseline boilerplate (Phase-0, the monthly
    # monitor, and a standing podcast-outreach task), so a plan built from an EMPTY or failed gap
    # model still looks complete while carrying zero gap-derived work. Detect that from the gap model
    # itself -- every gap-CONTENT array empty -- rather than from work-order counts (some baseline
    # tasks carry a gap-like source), so the console/report can show "plan is degraded -- re-run the
    # gap model" instead of presenting boilerplate as a finished strategy.
    _GAP_CONTENT_KEYS = ("missing_owned_content", "schema_gaps", "thin_corroboration",
                         "surface_actions", "local_seo_gaps", "competitor_defense", "site_technical_gaps")
    gap_derived = [w for w in wos if (w.rationale or {}).get("gap_source", "baseline setup") != "baseline setup"]
    degraded = not any(gap.get(k) for k in _GAP_CONTENT_KEYS)
    if degraded:
        log.warning("assemble_plan business=%s: gap model produced NO gap-derived work orders "
                    "(baseline boilerplate only) -- gap synthesis is likely empty or failed.", bid)
    return {
        "business": {k: business.get(k) for k in ("name", "domain", "goal", "geo")},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "start_date": start.isoformat(),
        "summary": gap.get("summary", ""),
        "expected_timeline": {
            "first_visible_movement": "weeks 8-16 (retrieval-grounded engines first)",
            "durable_results": "months 4-6 on local/branded queries",
            "note": "Crowding-out, not suppression: results come from out-producing and "
                    "out-corroborating accurate content, not removing third-party views.",
        },
        "phases": phases,
        "metrics": METRICS,
        "monitoring_cadence": "Monthly Module 1 audit + diff -> client progress report.",
        "counts": {"total": len(wos), "auto": len(auto), "human": len(human),
                   "gap_derived": len(gap_derived)},
        "degraded": degraded,
        "work_orders": [w.__dict__ for w in wos],
    }


# ----------------------------------------------------------------------------
# DB + CLI
# ----------------------------------------------------------------------------


def _latest_gap(business_id: int) -> tuple[dict, dict]:
    with db() as conn:
        b = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        g = conn.execute(
            "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
    if not b:
        raise SystemExit(f"No business id {business_id}")
    if not g:
        raise SystemExit("No gap model yet -- run Module 1 gap-model first.")
    return dict(b), (g["model"] if isinstance(g["model"], dict) else json.loads(g["model"]))


def plan_cmd(business_id: int, start: Optional[str]) -> None:
    business, gap = _latest_gap(business_id)
    start_date = date.fromisoformat(start) if start else date.today()
    plan = assemble_plan(business, gap, start_date)
    # persist
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS strategy_plans ("
            "id BIGSERIAL PRIMARY KEY, business_id BIGINT, plan JSONB, created_at TIMESTAMPTZ DEFAULT now())"
        )
        conn.execute("INSERT INTO strategy_plans (business_id, plan) VALUES (%s,%s)",
                     (business_id, json.dumps(plan)))
        conn.commit()
    print(json.dumps(plan, indent=2))
    log.info("Plan: %d work orders (%d auto / %d human)",
             plan["counts"]["total"], plan["counts"]["auto"], plan["counts"]["human"])


def tools_cmd() -> None:
    by_cap: dict[str, list[Tool]] = {}
    for c in CAPABILITIES:
        by_cap[c] = registry_for(c)
    for cap, tools in by_cap.items():
        print(f"\n{cap}:")
        for t in tools:
            star = " *" if t == tools[0] else "  "
            print(f" {star} [{t.execution.value:6}] {t.name} -- {t.notes}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Strategy + work-order generator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("plan")
    pp.add_argument("--business-id", type=int, required=True)
    pp.add_argument("--start", help="ISO date the plan begins (default today)")
    sub.add_parser("tools")
    args = ap.parse_args()
    if args.cmd == "plan":
        plan_cmd(args.business_id, args.start)
    elif args.cmd == "tools":
        tools_cmd()


if __name__ == "__main__":
    main()
