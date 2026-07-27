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
    from . import textutils as _tu
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import textutils as _tu  # type: ignore

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
    # Rich-media capabilities (NotebookLM API + in-house LLM fallback path)
    "podcast_creation",    # Audio Overview: two-host AI podcast from audit data
    "slide_deck",          # Executive slide-deck brief from study-guide synthesis
    # "infographic" removed (owner decision) -- not a producible capability any more.
    "explainer_video",     # Explainer-video script from multi-source synthesis
    "research_brief",      # Deep research brief for PR / content teams
    "deep_content",        # Long-form articles, blog series, newsletters
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
    # NotebookLM (MANUAL for topic research; SEMI via API for rich-media generation)
    Tool("notebooklm", "NotebookLM", "topic_research", Exec.MANUAL,
         "Free (browser); synthesize source docs into briefs/audio. Use notebooklm_api for automated generation."),
    Tool("getgeni2", "Vadoo AI captions", "video_repurpose", Exec.MANUAL, "AppSumo; captions/clips."),

    # --- Rich-media generation via NotebookLM API (dormant-safe; LLM fallback when no key) ---
    Tool("notebooklm_api", "NotebookLM API", "podcast_creation", Exec.SEMI,
         "Google NotebookLM API; Audio Overview (two-host AI podcast) from audit + gap + competitor "
         "sources. Requires NOTEBOOKLM_API_KEY or GEMINI_API_KEY. Output: MP3 + transcript, pending_review."),
    Tool("notebooklm_api_slides", "NotebookLM API", "slide_deck", Exec.SEMI,
         "Google NotebookLM API; study-guide synthesis across audit sources -> 10-12 slide deck brief."),
    # infographic tool removed (owner decision) -- infographics are no longer produced.
    Tool("notebooklm_api_video", "NotebookLM API", "explainer_video", Exec.SEMI,
         "Google NotebookLM API; study-guide synthesis -> explainer-video script. Pair with a video production brief."),
    Tool("notebooklm_api_brief", "NotebookLM API", "research_brief", Exec.SEMI,
         "Google NotebookLM API; briefing-doc synthesis across audit/competitor sources -> PR/content research brief."),
    # In-house LLM path for deep written content (no external key required)
    Tool("llm_deep_content", "Engine-native LLM", "deep_content", Exec.AUTO,
         "System generates long-form articles, blog-series outlines, and newsletter briefs via the in-house LLM path."),
    # Veo (Google) for cinematic video generation when the Gemini/Veo key is set
    Tool("veo", "Google Veo", "video_creation", Exec.SEMI,
         "Google Veo (requires GEMINI_API_KEY with Veo access); short cinematic clips from the video-production "
         "brief. Output lands in pending_review before any use."),
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
    # rich-media CONTENT the strategist produces the most of -- these had no lever, so predict_impact
    # scored them 0 and they sorted LAST (and disagreed with gain_for/predict_plan/roadmap, which DO
    # credit them). Map each to its acceleration lever so ROI is real + consistent across surfaces.
    "explainer_video": "videos",
    "podcast_creation": "videos",
    "deep_content": "third_party_articles",
    "slide_deck": "third_party_articles",
    "research_brief": "third_party_articles",
    "press_outreach": "earned_press",
    "media_list_building": "earned_press",
    "link_building": "earned_links",
    "review_generation": "reviews",
    "social_publishing": "third_party_articles",
    "gbp_optimization": "reviews",
    # structural / tracking tasks have no direct per-unit score lever
    "schema_markup": None,
    "technical_seo": None,
    "ai_visibility_tracking": None,
}
# Qualitative SEO impact (point prediction for local rank isn't reliable yet, so we keep it honest).
_CAPABILITY_SEO = {
    "local_content_creation": "High", "gbp_optimization": "High", "link_building": "High",
    "schema_markup": "Medium", "content_writing": "Medium", "review_generation": "Medium",
    "press_outreach": "Medium", "video_creation": "Medium", "explainer_video": "Medium",
    "deep_content": "Medium", "research_brief": "Medium",
    "podcast_creation": "Low", "slide_deck": "Low",
    "social_publishing": "Low", "media_list_building": "Low", "technical_seo": "Medium",
    "ai_visibility_tracking": "—",
}

# Effort weight per capability (1 = quick, 3 = heavy lift) for ROI ranking (item 5D). ROI =
# impact x confidence / effort, so a high-impact, high-confidence, low-effort task ranks first.
_EFFORT = {
    "schema_markup": 1, "ai_visibility_tracking": 1, "social_publishing": 1, "gbp_optimization": 1,
    "review_generation": 2, "content_writing": 2, "local_content_creation": 2, "media_list_building": 2,
    "deep_content": 2, "slide_deck": 2, "research_brief": 2, "technical_seo": 2,
    "video_creation": 3, "explainer_video": 3, "podcast_creation": 3, "press_outreach": 3, "link_building": 3,
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
# The single source of truth for "producible CONTENT" -- a draftable/generatable piece (article, video,
# podcast, blog series, slide deck, infographic, research brief). BOTH the strategy view's content specs
# AND the Content "To Produce" section derive from THIS set, so the two can never disagree. Technical /
# structural work (schema, site speed/freshness/titles, internal links, alt-text, link building) is
# deliberately NOT content -- it belongs on the website-fixes board, never in the content section.
CONTENT_CAPABILITIES = frozenset({
    "content_writing", "video_creation", "explainer_video", "deep_content",
    "podcast_creation", "slide_deck", "research_brief", "local_content_creation",
})  # NOTE: "infographic" removed by owner decision -- not a producible content type any more.

_CAPABILITY_AREA = {
    # producible content -> the Content "To Produce" section
    "content_writing": "content", "video_creation": "content", "explainer_video": "content",
    "deep_content": "content", "podcast_creation": "content", "slide_deck": "content",
    "research_brief": "content",
    "local_content_creation": "local",          # a local page-1 PROGRAM (its own area)
    # website / technical -- NOT content (website-fixes board)
    "schema_markup": "website", "technical_seo": "website", "link_building": "website",
    "press_outreach": "outreach", "media_list_building": "outreach",
    "social_publishing": "social",
    "review_generation": "reviews",
    "gbp_optimization": "local",
    "ai_visibility_tracking": "tracking",
}

# Topics an LLM sometimes emits as "missing_owned_content" that are actually TECHNICAL/structural site
# work (not a draftable article) -- route these to technical_seo so they don't render as content.
import re as _re_tech
_TECHNICAL_TOPIC_RE = _re_tech.compile(
    r"\b(internal link|alt[- ]?text|image (audit|optimi|quality)|site[- ]?wide (image|link|audit)|"
    r"page ?speed|core web vital|\blcp\b|\bcls\b|\bttfb\b|canonical|sitemap|robots\.txt|redirect|"
    r"crawl budget|index(ation|ing)?|url structure|duplicate content|301|meta (tag|description) audit)\b",
    _re_tech.I)


def predict_impact(business_id: int, capability: str) -> dict:
    """Estimate one task's impact: predicted AI-score points (from learned-or-baseline lever
    effectiveness) + a qualitative SEO impact. Honest about basis + confidence; best used to RANK
    tasks by return, and snapshotted so we can later compare predicted vs measured."""
    lever = _CAPABILITY_TO_LEVER.get(capability)
    ai_points = None
    basis = ""
    confidence = "low"
    if lever:
        # ONE canonical gain source (roi_predictor.gain_for): this-client learned -> cross-client
        # prior -> static baseline, correctly normalized to 0-100 POINTS (the old code here used *100,
        # 2x too high, while roadmap/predict_plan used the ga value as points, ~50x too low). Routing
        # both through gain_for makes plan-ROI and roadmap-ROI agree.
        try:
            from . import roi_predictor as _roi
            ai_points, basis, confidence = _roi.gain_for(capability, business_id)
            if basis == "this client":
                basis = "measured from your results"
        except Exception:  # noqa: BLE001 -- prediction must never break planning
            ai_points, basis, confidence = None, "", "low"
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


# Common words that must NOT count toward coverage overlap -- otherwise 'the/for/your/best/how' shared
# between a gap topic and any campaign piece produced false 2-token matches that silently DROPPED the
# dedicated gap task. len>2 keeps domain acronyms (tax/ira/etf/roi/seo/gbp/cpa/llc).
_STRAT_STOP = {"the", "for", "your", "our", "and", "with", "how", "what", "why", "who", "best", "top",
               "near", "you", "are", "does", "vs", "guide", "page", "content", "about", "help", "get"}


def _strat_tokens(s: str) -> set[str]:
    """Significant, stopword-stripped tokens for coverage matching between a flat gap item and the
    strategist's campaign pieces (so we only absorb a gap item a campaign really addresses -- never DROP
    one it missed)."""
    return {t for t in _re_tech.findall(r"[a-z0-9]+", (s or "").lower())
            if len(t) > 2 and t not in _STRAT_STOP}


def _emit_typed_program(add, topic: str, atype: str, gap_source: str, why: str, gap_key: str,
                        default_types=None) -> None:
    """Emit the SAME multi-type content spread the BATCH path (content_batch._types_for_gap) fans an
    uncovered moc/competitor gap into, so plan and batch produce the same content-type SET for one
    gap_key (was 1 WO on the plan vs ~4 typed pieces in the batch -- a plan-vs-batch divergence). Each
    piece shares the canonical gap_key (measured together) and carries its content_type so generation
    uses the right per-type template; social is atomized from the long-form, not a standalone WO.
    `default_types` MUST be the tenant's profile default_content_types (the same value the batch passes)
    so the type SET matches for non-module-default tenants (generic keeps faq / drops white_paper)."""
    _cb_t = None
    try:
        from . import content_batch as _cb_t
        types = _cb_t._types_for_gap({"topic": topic, "asset_type": atype}, default_types) or ["article"]
    except Exception:  # noqa: BLE001
        types = ["article"]
    _titles = {"blog": f"Blog: {topic}", "white_paper": f"White paper: {topic}", "faq": f"{topic}: FAQ",
               "landing_page": f"{topic} — overview page", "video_script": f"Video: {topic}",
               "article": f"Create owned asset: {topic}"}
    _nonsocial = [t for t in types if t != "social_post"]
    for k, ct in enumerate(_nonsocial):
        cap = "video_creation" if (ct == "video_script" or "video" in (atype or "").lower()) else "content_writing"
        add(_titles.get(ct, f"Create owned asset: {topic} ({ct})"), cap,
            f"Produce a {ct} on '{topic}'. Rationale: {why}. Draft via engine-native LLM; fact-check "
            f"trust-sensitive claims; publish on the business domain.{_AEO_CHECKLIST}", 3,
            gap_source=gap_source, why=why, source_query=topic, gap_key=gap_key,
            # Shared hub rule with the batch path (content_batch.pillar_role) so the plan + the produced
            # batch designate the SAME piece as the pillar (was: first-emitted vs first-article-like).
            campaign={"content_type": ct,
                      "role": (_cb_t.pillar_role(ct, _nonsocial) if _cb_t else ("pillar" if k == 0 else "cluster")),
                      "ordinal": k})


def build_work_orders(gap: dict, business=None, strategy: Optional[dict] = None) -> list[WorkOrder]:
    wos: list[WorkOrder] = []
    n = 0
    # Media/press angles must reflect THIS business's geo + industry, never a hardcoded example.
    biz = business or {}
    geo = (biz.get("geo") or "").strip() or "your local area"
    industry = (biz.get("industry") or "").strip() or "local-business"
    # The tenant's profile content spread -- resolved the SAME way the batch (for_business) and strategist
    # do, INCLUDING any persisted strategy_profile.default_content_types override, so an uncovered moc/comp
    # gap emits the identical content-type SET on plan and batch even when an operator has customized it
    # (derive(biz) alone drops the override).
    _prof_types = None
    try:
        from . import business_profile as _bp_t
        if biz.get("id"):
            _prof_types = (_bp_t.for_business(biz["id"]) or {}).get("default_content_types")
        else:
            _prof_types = (_bp_t.derive(biz) if biz else {}).get("default_content_types")
    except Exception:  # noqa: BLE001 -- profile is best-effort; None -> module default spread (same as batch)
        _prof_types = None
    # New-domain proxy (same signal content_strategist.plan uses for cadence): few published pieces ->
    # 'new', so backlink velocity uses the SAFETY-capped 2-4 RD/mo band instead of an unsafe 4-8 for a
    # thin-inventory tenant. Fail-safe -> 'established' (no throttle) if the count can't be read.
    _new_domain = False
    try:
        if biz.get("id"):
            with db() as _c_nd:
                _pub = _c_nd.execute(
                    "SELECT COUNT(*) n FROM content_drafts WHERE business_id=%s AND status IN "
                    "('approved','published')", (biz["id"],)).fetchone()["n"]
            _new_domain = _pub < 3
    except Exception:  # noqa: BLE001
        _new_domain = False
    # When the Content Strategist produced a program, its cluster CAMPAIGNS replace the deterministic
    # one-WO-per-gap owned-content + competitor-defense loops (the strategist read those same gaps and
    # fanned them into a real multi-piece program). Everything else (baseline, schema, corroboration,
    # rich-media, social, local page-1, site-technical, monitor) is unchanged. A strategist outage ->
    # strategy is falsy -> the original template runs, so planning never breaks.
    has_strategy = bool(strategy and strategy.get("campaigns"))
    # Topics the strategist's campaigns already cover (token sets of every piece's title + target
    # query + the campaign topic). We skip a flat gap item ONLY when a campaign actually addresses it
    # -- an owned-content / competitor gap the strategist MISSED still gets its own task, so the plan
    # never loses a foundational topic (owner rule: err toward too much content, never too little).
    _covered_tokens: list[set] = []
    _covered_commercial: list[set] = []   # token sets of comparison / commercial-intent pieces only
    if has_strategy:
        for _camp in strategy.get("campaigns", []):
            _c_intent = (_camp.get("intent") or "").lower()
            _covered_tokens.append(_strat_tokens(_camp.get("topic", "")))
            for _pc in (_camp.get("pieces") or []):
                _pt = _strat_tokens(f"{_pc.get('title', '')} {_pc.get('target_query', '')}")
                _covered_tokens.append(_pt)
                if _pc.get("role") == "comparison" or _c_intent in ("commercial", "transactional"):
                    _covered_commercial.append(_pt)

    def _covered(text: str, *, commercial: bool = False) -> bool:
        """A flat gap item is 'covered' by the strategist ONLY when a campaign piece shares a MAJORITY of
        the gap's significant tokens (>= max(2, 60%)), not just any 2 -- so a loose word overlap can't
        silently drop a real gap task. `commercial=True` (competitor-defense) further requires the match
        to come from a comparison / commercial-intent piece that actually competes for the query."""
        t = _strat_tokens(text)
        if not t:
            return False
        need = max(2, round(0.6 * len(t)))
        pool = _covered_commercial if commercial else _covered_tokens
        return any(len(t & c) >= need for c in pool)

    def add(title, capability, instruction, week, deps=None, *, gap_source="baseline setup", why="",
            source="audited gap", area=None, platform="", source_query="", campaign=None,
            execution=None, gap_key=None):
        # Foundational Phase-0 tasks (AI-visibility baseline, GBP claim, review sequence) legitimately
        # trace to no single gap, so they default to gap_source='baseline setup' -> the console shows
        # "From: baseline setup" instead of a blank "why". Gap-derived add() calls pass gap_source
        # explicitly and override this default (audit report Low-19).
        nonlocal n
        n += 1
        tool = best_tool(capability)
        alts = [t.name for t in registry_for(capability)[1:4]]
        # source_query links a task to the worst AI query/topic it fixes; campaign (optional) carries
        # the strategist's campaign linkage (id/role/topic/intent/publish_week) so the strategy view
        # can group a campaign's pillar + clusters into one tree and the calendar can drip them.
        specifics = {}
        if source_query:
            specifics["source_query"] = source_query
        if campaign:
            specifics.update(campaign)
        # Stamp the CANONICAL gap key (same scheme as content_batch.gaps_for_business: local:/moc:/comp:)
        # so every piece of a PROGRAM shares ONE content_impact batch and the gap-completion meter joins
        # the batch to the real gap. Without this, ensure_impact_batch fell back to gid("moc", <title>),
        # giving each piece its own single-piece batch that matched no canonical gap (no collective
        # measurement + the gap showed 0 content produced).
        if gap_key:
            specifics["gap_key"] = gap_key
        wos.append(WorkOrder(
            wo_id=f"WO-{n:03d}", title=title, capability=capability,
            # execution override lets an opt-in piece (e.g. a per-campaign video plan) be 'manual'
            # so it isn't auto-drafted in a batch -- the owner generates it on click.
            execution=(execution or (tool.execution.value if tool else "manual")),
            recommended_tool=(tool.name if tool else None),
            alternatives=alts,
            instruction=instruction, phase=_phase_for_week(week), week=week,
            depends_on=deps or [],
            rationale={"gap_source": gap_source, "why": why, "source": source,
                       **({"campaign_rank": campaign["campaign_rank"]} if campaign and "campaign_rank" in campaign else {})},
            why_helps_ai_rep=_WHY_AI.get(capability, ""),
            why_helps_seo=_WHY_SEO.get(capability, ""),
            area=area or _CAPABILITY_AREA.get(capability, "other"),
            platform=platform,
            gap_specifics=specifics,
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

    # --- Content Strategist PROGRAM: the multi-piece content campaigns (pillar + clusters + comparison)
    # that REPLACE the old 1-WO-per-gap owned-content + competitor-defense loops. Each piece is a real,
    # draftable content asset; campaign metadata rides in gap_specifics so the strategy view groups a
    # campaign's pillar + clusters into one tree and the calendar can drip them by publish_week. A
    # constant gap_source + the per-piece target_query keep each task's identity stable across re-plans
    # (sync_plan keys on capability|gap_source|source_query), independent of the rank-based campaign id.
    if has_strategy:
        for camp in strategy.get("campaigns", []):
            cmeta = {"campaign_id": camp.get("id"), "campaign_topic": camp.get("topic"),
                     "campaign_intent": camp.get("intent"), "campaign_rank": camp.get("priority_rank", 0),
                     "funnel_stage": camp.get("funnel_stage")}
            # The campaign's real gap origin (missing owned content / competitor analysis / topical
            # authority / keyword intent) for the "From:" traceability, instead of a generic label.
            _camp_gs = f"content strategy: {camp.get('gap_source')}" if camp.get("gap_source") else "content strategy"
            # ONE stable program key per campaign (from its topic, not the rank-based id) so every piece
            # -- pillar + all clusters -- shares a single content_impact batch and the campaign is
            # measured as a program. Surfaces via gap_completion's campaign/cluster batch rollup.
            _camp_gk = _tu.gid("camp", camp.get("topic") or camp.get("id") or "")
            for pc in (camp.get("pieces") or []):
                title = pc.get("title") or camp.get("topic") or "Content piece"
                role = pc.get("role") or "cluster"
                add(title, pc.get("capability") or "content_writing",
                    f"{pc.get('why') or camp.get('why') or ''} This is the {role} of the "
                    f"'{camp.get('topic')}' content campaign — a {pc.get('content_type') or 'article'} "
                    f"answering: {pc.get('target_query') or title}. Draft via engine-native LLM; "
                    f"fact-check trust-sensitive claims; publish on the business domain.{_AEO_CHECKLIST}",
                    int(pc.get("week") or 3),
                    gap_source=_camp_gs, why=pc.get("why") or camp.get("why") or "",
                    source_query=pc.get("target_query") or title, gap_key=_camp_gk,
                    # ordinal (stable per campaign) drives a churn-proof task key across re-plans.
                    campaign={**cmeta, "role": role, "publish_week": pc.get("week"),
                              "content_type": pc.get("content_type"), "ordinal": pc.get("ordinal")},
                    # Per-campaign video plans are opt-in: 'manual' so they surface as options but
                    # aren't auto-drafted in a batch -- the owner generates the script (+ captions +
                    # VideoObject schema) and renders the MP4 on click.
                    execution=("manual" if pc.get("on_click") else None))
            # Materialize the atomization (repurposing) plan into opt-in work orders (email/newsletter)
            # so "create once, distribute many" is real work, not a stored-then-ignored spec. Social
            # atoms are NOT auto-created on approve -- atomize_draft runs only inside content_batch or via
            # the explicit /atomize endpoint (surfaced as the "Create social posts" action on To-Produce).
            # Opt-in (manual) -> generate on click.
            # NOTE: infographics are intentionally NOT materialized -- the owner removed infographics
            # from the content strategy (NotebookLM can't render an infographic image and the platform
            # doesn't produce one), so any `atomization.infographic` the planner emits is ignored.
            _atom = camp.get("atomization") if isinstance(camp.get("atomization"), dict) else {}
            _bw = int((camp.get("pieces") or [{}])[0].get("week") or 4) + 1
            if _atom.get("email"):
                add(f"Email / newsletter: {camp.get('topic')}", "deep_content",
                    f"A newsletter/email built from the '{camp.get('topic')}' pillar to nurture the "
                    f"list.{_AEO_CHECKLIST}", _bw,
                    gap_source=_camp_gs, why=camp.get("why") or "",
                    campaign={**cmeta, "role": "email", "ordinal": 0}, execution="manual")

    # --- Phase 1: owned content for each missing topic + schema ---
    for i, item in enumerate(gap.get("missing_owned_content", []) or []):
        topic = item.get("topic", f"topic {i+1}")
        atype = item.get("asset_type", "article")
        why = item.get("why", "")
        # Some LLM-emitted "missing content" items are really TECHNICAL site work (internal-link audit,
        # alt-text/image audit, page-speed) -- route those to technical_seo so they land on the website-
        # fixes board, not the content section as a fake article. (This runs even WITH a strategist plan
        # so technical items still reach the website-fixes board; only the CONTENT branch is absorbed.)
        if _TECHNICAL_TOPIC_RE.search(f"{topic} {atype}"):
            add(f"Fix site: {topic}", "technical_seo",
                f"On-site technical work: {why or topic}. Not a draftable article -- implement on the "
                f"website (dev/SEO task).", 3, gap_source="audited gap: site technical", why=why)
            continue
        # When a strategist campaign already COVERS this topic, skip the flat 1-per-gap content task
        # (the campaign produced a pillar + clusters for it). A topic no campaign covers still gets
        # its own task -- never dropped.
        if has_strategy and _covered(f"{topic} {atype}"):
            continue
        # Emit the SAME multi-type content spread the BATCH path (content_batch._types_for_gap) fans this
        # gap into, so plan and batch produce the same content-type SET for a moc: gap_key -- was 1 WO
        # here vs ~4 typed pieces in the batch (a plan-vs-batch divergence). All share the canonical
        # gap_key so they measure together.
        _emit_typed_program(add, topic, atype, "audited gap: missing owned content", why,
                            _tu.gid("moc", topic), default_types=_prof_types)
    for sg in gap.get("schema_gaps", []) or []:
        add(f"Add schema: {sg}", "schema_markup",
            f"Generate and deploy JSON-LD ({sg}) on the relevant pages so answer engines "
            f"can cleanly extract facts.", 4, gap_source="audited gap: schema", source_query=str(sg))

    # --- Crowd-out sizing: how much positive content to publish to BURY the page-1 negatives ---
    # This is the engine's core reputation goal, so it must be sized from ORM evidence
    # (content_research.displacement_pages_for: ~8-12 positive assets per page-1 negative in 90 days,
    # more for a high-authority negative), NOT left implicit. Count negatives from the gap model
    # (competitor-won queries + a contested/negative narrative); emit a concrete, sized crowd-out target
    # (the last previously-dead sibling helper -> a stated, size-driving decision).
    _num_neg = len(gap.get("competitor_defense") or []) + (1 if (biz.get("contested_terms") or "").strip() else 0)
    # A page-1 negative on a HIGH-AUTHORITY domain (major news, gov, large review/complaint sites, a
    # lawsuit/regulatory filing) is far harder to displace and takes ~1.5-2x the volume. Detect it from the
    # negative narrative text (the gap model carries no domain-authority field yet), so displacement_pages_for's
    # multiplier -- previously DEAD because no caller passed it -- actually fires for a serious negative.
    _neg_txt = " ".join([
        (biz.get("contested_terms") or ""),
        " ".join(str(c.get("query", "")) + " " + str(c.get("why", "")) + " " + str(c.get("recommendation", ""))
                 for c in (gap.get("competitor_defense") or []) if isinstance(c, dict)),
    ]).lower()
    _high_auth = bool(_re_tech.search(
        r"\b(lawsuit|sued|litigation|settlement|indict|sec |finra|regulator|attorney general|"
        r"class action|news|times|post|tribune|journal|reuters|bloomberg|\.gov|ripoff|"
        r"bbb|trustpilot|glassdoor|reddit|complaint)\b", _neg_txt))
    _dp_lo = _dp_hi = 0
    if _num_neg > 0:
        try:
            from . import content_research as _cr_disp
            _dp_lo, _dp_hi, _dp_src = _cr_disp.displacement_pages_for(_num_neg, high_authority=_high_auth)
            add("Crowd-out plan: out-publish the negative results", "content_writing",
                f"To bury the {_num_neg} page-1 negative(s{', high-authority' if _high_auth else ''}), publish "
                f"~{_dp_lo}-{_dp_hi} original positive/earned, indexed assets in the first 90 days ({_dp_src}) "
                f"-- enough to control 8-10 of the 10 page-1 slots. This is the FLOOR the pillar/cluster + "
                f"local programs above should sum to; front-load them.{_AEO_CHECKLIST}", 2,
                gap_source="reputation crowd-out", source_query="crowd-out volume", execution="manual")
        except Exception:  # noqa: BLE001 -- best-effort sizing line
            _dp_lo = _dp_hi = 0

    # --- Phase 2: corroboration (press, media list, partner, link) ---
    if gap.get("thin_corroboration"):
        add("Build local media list", "media_list_building",
            f"Assemble a {geo} {industry} journalist + local-outlet list, with pitch angles drawn "
            f"from this business's real differentiators and community involvement (what makes it "
            f"credible and locally newsworthy).", 5,
            gap_source="audited gap: thin corroboration", source_query="local media list")
        # Link-building velocity is RESEARCH-sized (content_research.backlink_target_for): a NEW
        # referring-domains/month target, severity-scaled like video/podcast/cadence, so the earned-link
        # line carries a concrete cited target instead of a purely qualitative instruction (the helper was
        # otherwise computed-but-never-called).
        try:
            from . import content_research as _cr_bl
            from . import content_strategist as _cs_bl
            _bl_sevs = [(c.get("severity") or 0) for c in (strategy.get("campaigns", []) if has_strategy else [])]
            _bl_norm = min(1.0, (max(_bl_sevs) if _bl_sevs else 0) / float(max(1, _cs_bl._CLUSTER_FLOOR_SEVERITY * 2)))
            _bl_lo, _bl_hi, _bl_src = _cr_bl.backlink_target_for(
                authority=("new" if _new_domain else "established"), severity=_bl_norm)
            _bl_line = (f"Target ~{_bl_lo}-{_bl_hi} NEW referring domains/month ({_bl_src}) via the media "
                        f"list + guest posts / digital PR -- referring-domain count is the strongest-"
                        f"correlated ranking lever. Never buy links or spike velocity.")
        except Exception:  # noqa: BLE001
            _bl_line = ("Earn new referring domains steadily via the media list + guest posts / digital PR; "
                        "never buy links or spike velocity.")
        add("Earn editorial backlinks (digital PR)", "link_building", _bl_line + _AEO_CHECKLIST, 6,
            gap_source="audited gap: thin corroboration", source_query="referring domains", execution="manual")
        for i, claim in enumerate(gap.get("thin_corroboration", [])):
            c = claim.get("claim", f"claim {i+1}")
            where = claim.get("where_to_get_it", "")
            add(f"Corroborate: {c}", "press_outreach",
                f"Secure third-party coverage/mention supporting '{c}'. Source: {where}. "
                f"Draft pitch; route via outreach tool; human approves before send.", 6,
                gap_source="audited gap: thin corroboration", why=c, source_query=c)
    # Podcast-appearance volume is RESEARCH-sized (content_research.podcast_appearance_target: quarterly
    # floor -> 1-2/mo) AND SEVERITY-SCALED like the other non-text surfaces (video/cadence/backlink), so a
    # bigger reputation problem books more appearances -- not a hardcoded 3-5 or a flat 0.5 severity.
    try:
        from . import content_research as _cr_pod
        from . import content_strategist as _cs_pod
        _sevs = [(c.get("severity") or 0) for c in (strategy.get("campaigns", []) if has_strategy else [])]
        # Normalize against the SHARED, env-tunable severity gate (same divisor video + cadence use), so
        # podcast severity-scaling can't desync from them when STRATEGIST_CLUSTER_FLOOR_SEVERITY is changed.
        _sev_div = float(max(1, _cs_pod._CLUSTER_FLOOR_SEVERITY * 2))
        _sev_norm = min(1.0, (max(_sevs) if _sevs else 0) / _sev_div)
        _pl, _ph, _psrc = _cr_pod.podcast_appearance_target(severity=_sev_norm, months=12)
        _pod_line = f"Book ~{_pl}-{_ph} relevant {geo} / {industry} guest podcast appearances over the year ({_psrc})"
    except Exception:  # noqa: BLE001
        _pod_line = f"Identify 3-5 relevant {geo} / {industry} podcasts"
    add(f"Book relevant podcast appearances ({industry})", "press_outreach",
        f"{_pod_line}; pitch the principal as guest; publish a transcript page per episode (audio alone "
        f"isn't AI-citable) so each yields an indexed third-party positive page.", 7,
        gap_source="audited gap: thin corroboration", source_query="podcast appearances")

    # --- Phase 2: rich-media amplification via NotebookLM API + in-house LLM ---
    # Always emitted so the strategy surfaces every available channel. Execution is AUTO/SEMI
    # (per TOOL_REGISTRY). Auto-runs when AGENT_RICH_MEDIA_IN_CYCLE=1, or via the "Generate draft"
    # button (generate_for_wo routes these capabilities to rich_media_generator). Text-only types
    # need no external key; NotebookLM types require NOTEBOOKLM_API_KEY or GEMINI_API_KEY and fall
    # back to the in-house LLM when absent — so the whole block is dormant-safe.
    # Bind each rich-media synthesis piece to the HIGHEST-SEVERITY campaign (C01) it amplifies -- real
    # target query, real gap_source, campaign metadata -- so it nests under that campaign's tree with a
    # human reason, instead of the old "Other" bucket with a capability-label as its fake query. When the
    # strategist is unavailable (no campaigns) they fall back to standalone WOs with human instruction/why.
    _rich_specs = [
        ("deep_content", "Generate deep-content bundle (long-form article + blog series + newsletter)",
         "A 1,500-2,500 word thought-leadership article + three blog outlines + a newsletter that amplify "
         "the '{t}' campaign so AI answer engines have deep, citable owned content on it.", 6),
        ("podcast_creation", "Generate AI reputation podcast (Audio Overview)",
         "A two-host AI podcast (Audio Overview) on the '{t}' campaign, synthesised from the audit + gap "
         "model + strategy -- an audio format that widens reach and reinforces authority.", 7),
        ("slide_deck", "Generate executive slide-deck brief",
         "A 10-12 slide executive deck brief on the '{t}' campaign for sales/partner enablement.", 8),
        ("research_brief", "Generate PR/content-team research brief",
         "A deep research brief on the '{t}' campaign for PR teams / journalists to pitch earned coverage.", 8),
    ]
    _rich_campaigns = strategy.get("campaigns", []) if has_strategy else []
    if _rich_campaigns:
        _c0 = _rich_campaigns[0]
        _c0meta = {"campaign_id": _c0.get("id"), "campaign_topic": _c0.get("topic"),
                   "campaign_intent": _c0.get("intent"), "campaign_rank": _c0.get("priority_rank", 0),
                   "funnel_stage": _c0.get("funnel_stage")}
        _c0q = (_c0.get("target_queries") or [_c0.get("topic")])[0] or _c0.get("topic") or "reputation"
        _c0gs = f"content strategy: {_c0.get('gap_source', '') or 'amplification'}"
        _c0topic = _c0.get("topic") or "your top campaign"
        # Share campaign C0's CANONICAL camp: gap_key (same scheme its pillar/cluster pieces use) so the
        # rich-media amplification pieces join C0's collective impact batch + earn its gap-completion
        # credit -- not a divergent moc:<query> batch ensure_impact_batch would otherwise derive.
        _c0gk = _tu.gid("camp", _c0.get("topic") or _c0.get("id") or "")
        for _ri, (_cap, _title, _instr, _wk) in enumerate(_rich_specs):
            add(_title, _cap, _instr.format(t=_c0topic) + _AEO_CHECKLIST, _wk,
                gap_source=_c0gs, why=f"Amplifies the '{_c0topic}' campaign in another format.",
                source_query=_c0q, gap_key=_c0gk,
                campaign={**_c0meta, "role": "amplify", "content_type": _cap,
                          "publish_week": _wk, "ordinal": 50 + _ri}, execution="manual")
    else:
        for _cap, _title, _instr, _wk in _rich_specs:
            add(_title, _cap, _instr.format(t="your reputation") + _AEO_CHECKLIST, _wk,
                gap_source="rich-media amplification",
                why="A rich-media format that widens reach and reinforces authority.",
                source_query=f"reputation {_cap.replace('_', ' ')}")
    # Infographics were removed from the content strategy (owner decision). The explainer VIDEO is now
    # emitted per-campaign by the strategist (content_strategist._add_video_plan), gated on its
    # atomization.video_script judgment -- not as a standalone baseline piece.

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

    # --- Local-SEO gaps -> a specific multi-piece LOCAL PROGRAM (a geo landing PAGE + supporting BLOGS
    # (one per ranking keyword) + an FAQ), all grouped under ONE synthetic `local:` campaign so the
    # strategy view renders the program's actual pieces (like a campaign's pillar+cluster tree) instead
    # of one flat "Reach page 1 for X" bucket. Reuses content_batch._local_keywords for the spoke set. ---
    _biz_id = biz.get("id")
    try:
        from . import content_batch as _cb_local
    except Exception:  # noqa: BLE001 -- keyword enrichment is best-effort; the pillar still emits
        _cb_local = None
    for i, g in enumerate(gap.get("local_seo_gaps", []) or []):
        q = g.get("query", f"local query {i + 1}")
        rec = g.get("recommendation", "Create geo-specific content + strengthen GBP / local citations.")
        why_l = g.get("why", "")
        _cid = "local:" + (_re_tech.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:48] or f"gap{i}")
        _lmeta = {"campaign_id": _cid, "campaign_topic": q, "campaign_intent": "local",
                  "campaign_rank": 100 + i, "funnel_stage": "decision"}
        # The CANONICAL local gap key (matches content_batch.gaps_for_business) so the whole program --
        # pillar + every spoke + FAQ -- shares ONE content_impact batch and the completion meter credits
        # this real local gap, measuring whether the PROGRAM moved the ranking (not each piece alone).
        _local_gk = _tu.gid("local", q)
        # PILLAR: the geo landing page that must rank for the query.
        add(f"Local page: {q}", "local_content_creation",
            f"{rec} Current position: {g.get('current_rank', 'off page 1')}.{_AEO_CHECKLIST}", 4,
            gap_source="local search ranking", why=why_l, source_query=q, gap_key=_local_gk,
            campaign={**_lmeta, "role": "pillar", "content_type": "local_page", "publish_week": 4, "ordinal": 0})
        # SPOKES: supporting blogs sized DYNAMICALLY by competitiveness via the SAME shared helper the
        # batch path uses (content_batch.local_spoke_target + _local_spokes) -- real ranking keywords
        # first, then distinct local sub-topic angles to the target. A harder geo ranking earns more
        # content; an easier one fewer. Plan and batch now compute local size identically (no divergence).
        spokes_l: list = []
        if _cb_local is not None and _biz_id is not None:
            try:
                spokes_l = _cb_local._local_spokes(_biz_id, q, _cb_local.local_spoke_target(_biz_id, q)) or []
            except Exception:  # noqa: BLE001
                spokes_l = []
        for j, sp in enumerate(spokes_l):
            kw = sp.get("topic") if isinstance(sp, dict) else str(sp)
            if not kw:
                continue
            add(f"Blog: {kw}", "content_writing",
                f"A supporting blog answering '{kw}' that links up to the '{q}' local page.{_AEO_CHECKLIST}",
                5 + (j // 3),
                gap_source="local search ranking", why=f"Builds local topical authority for '{q}'.",
                source_query=kw, gap_key=_local_gk,
                campaign={**_lmeta, "role": "cluster", "content_type": "blog",
                          "publish_week": 5 + (j // 3), "ordinal": j + 1})
        # FAQ: the People-Also-Ask block for the local query.
        add(f"FAQ: {q}", "content_writing",
            f"An FAQ answering the top questions people ask about '{q}' in this area.{_AEO_CHECKLIST}", 6,
            gap_source="local search ranking", why=why_l, source_query=f"{q} faq", gap_key=_local_gk,
            campaign={**_lmeta, "role": "cluster", "content_type": "faq", "publish_week": 6, "ordinal": 90})
        # Competitiveness proxy: local_spoke_target sizes the spoke count by keyword difficulty, so a
        # program that earned more than the research band MIN (~8) is a competitive local market -> a
        # higher review-velocity target below.
        _local_competitive = len(spokes_l) >= 10
        # GBP + reviews: the PRIMARY local-ranking levers. Bind them to THIS local gap (same gap_key +
        # campaign) so a page-1 program always includes the Google Business Profile + review work, not
        # just content -- content alone rarely wins the local pack. (Was only emitted, un-linked, in the
        # separate surface_actions loop and only if the gap model happened to populate it.)
        add(f"Optimize Google Business Profile for '{q}'", "social_publishing",
            f"Complete/dial in the GBP for '{q}': correct categories, services, service-area, photos, "
            f"NAP consistency, Q&A, and weekly GBP posts -- the primary local-pack ranking lever.", 4,
            gap_source="local search ranking", why=why_l, source_query=q, gap_key=_local_gk,
            area="local", platform="gbp",
            campaign={**_lmeta, "role": "gbp", "publish_week": 4, "ordinal": 95})
        # Sized review velocity: reviews are a top local-pack + sentiment signal, so target a RESEARCH-
        # backed rate scaled by local competitiveness + the page-1 negatives to out-weigh (content_research
        # .review_velocity_target) -- not a bare "get reviews" ask with no number.
        try:
            from . import content_research as _cr_rev
            _rv_lo, _rv_hi, _rv_src = _cr_rev.review_velocity_target(
                num_negatives=_num_neg, competitive=bool(_local_competitive))
            _rev_line = (f"Run the review-request sequence so happy local clients leave Google reviews "
                         f"mentioning the service + locale for '{q}'. Target ~{_rv_lo}-{_rv_hi} NEW reviews/"
                         f"month ({_rv_src})")
        except Exception:  # noqa: BLE001
            _rev_line = (f"Run the review-request sequence so happy local clients leave Google reviews "
                         f"mentioning the service + locale for '{q}' -- review count/recency/velocity is a "
                         f"top local-pack signal")
        add(f"Drive Google reviews for '{q}'", "review_generation", _rev_line + ".", 4,
            gap_source="local search ranking", why=why_l, source_query=q, gap_key=_local_gk,
            area="local", campaign={**_lmeta, "role": "reviews", "publish_week": 4, "ordinal": 96})

    # --- Competitor-defense gaps -> tasks (questions a rival wins and you don't) ---
    # Absorbed into the strategist's campaigns when one COVERS the query (comparison / defense
    # content); an uncovered query still gets its own task, and the flat loop is the no-strategist
    # fallback.
    for i, g in enumerate(gap.get("competitor_defense", []) or []):
        q = g.get("query", f"query {i + 1}")
        # A competitor-won query is only 'covered' when a comparison / commercial piece actually competes
        # for it -- an informational pillar sharing a few words does NOT defend the query, so keep the task.
        if has_strategy and _covered(q, commercial=True):
            continue
        # Same multi-type spread the batch fans a comp: gap into (commercial: landing/comparison + article
        # + social), so plan and batch produce the same content-type SET for one comp: gap_key.
        _why_c = (f"{g.get('recommendation', 'Publish accurate owned content that answers this question well.')} "
                  f"A competitor ({g.get('competitor', 'a rival')}) appears here and you don't.")
        _emit_typed_program(add, q, "comparison", "competitor analysis", _why_c, _tu.gid("comp", q),
                            default_types=_prof_types)

    # --- Site-technical gaps -> tasks (thin/missing pages, schema, weak coverage) ---
    for i, g in enumerate(gap.get("site_technical_gaps", []) or []):
        issue = g.get("issue", f"site issue {i + 1}")
        rec = g.get("recommendation", "Fix the on-site issue so AI engines can extract your facts.")
        # A site-crawl technical gap is NEVER a draftable article: schema -> schema_markup, everything
        # else (LCP/speed, freshness dates, title alignment, duplicate URLs, front-loading) -> technical_seo.
        scap = "schema_markup" if "schema" in f"{issue} {rec}".lower() else "technical_seo"
        add(f"Fix site: {issue}", scap, rec, 3,
            gap_source="site crawl", why=g.get("why", ""))

    # --- Phase 3: steady-state monitoring + FRESHNESS ---
    add("Recurring AI-visibility monitor", "ai_visibility_tracking",
        "Schedule monthly Module 1 audit + diff; generate the monthly progress report.", 12)
    # Refresh clock: keep cornerstone content fresh on the RESEARCH-backed interval so AI engines keep
    # citing it (they cite recently-updated content far more). Makes content_research.refresh_interval_for
    # an actual scheduled decision, not a computed-then-ignored signal; GEO-tightened to <= quarterly.
    try:
        from . import content_research as _cr_ref
        _rlo, _rhi, _rsrc = _cr_ref.refresh_interval_for("competitive", goal="geo")
        add(f"Refresh cornerstone content (every ~{_rlo}-{_rhi} months)", "content_writing",
            f"On a ~{_rlo}-{_rhi} month clock, UPDATE the pillar/cornerstone pages -- refresh stats, dates, "
            f"and answers so AI engines keep citing them ({_rsrc}). Aim ~60% net-new / ~40% refresh of "
            f"existing pieces.{_AEO_CHECKLIST}", 12,
            gap_source="content freshness", source_query="content refresh", execution="manual")
    except Exception:  # noqa: BLE001 -- freshness WO is best-effort
        pass

    # --- Crowd-out floor RECONCILIATION (enforce, don't just narrate) ---
    # The displacement WO above states a FLOOR (how many owned assets are needed to bury the page-1
    # negatives). Previously nothing checked the plan actually MEETS it, so a plan could silently emit far
    # fewer owned pieces than its own stated floor. Count the owned indexable content pieces we emitted and,
    # if the program is under the floor, emit an explicit high-priority backfill task naming the exact
    # shortfall -- so the crowd-out volume is a measured, actionable gap, not advisory prose.
    if _dp_lo > 0:
        _owned = sum(1 for w in wos if getattr(w, "capability", "") in CONTENT_CAPABILITIES)
        if _owned < _dp_lo:
            _short = _dp_lo - _owned
            add("Crowd-out shortfall: add owned assets to reach the displacement floor", "content_writing",
                f"The plan currently emits {_owned} owned content asset(s) but the crowd-out FLOOR to bury "
                f"the {_num_neg} page-1 negative(s{', high-authority' if _high_auth else ''}) is {_dp_lo}-"
                f"{_dp_hi}. Produce ~{_short} MORE original, indexed positive assets (owned pages, FAQs, "
                f"videos, comparison/answer pages on the business's real strengths) in the first 90 days so "
                f"the program actually reaches the floor. Front-load these.{_AEO_CHECKLIST}", 2,
                gap_source="reputation crowd-out", source_query="crowd-out shortfall", execution="manual")
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


# The gap-model arrays that carry REAL, gap-derived work. If every one is empty, build_work_orders
# still emits baseline boilerplate (Phase-0 setup, the monthly monitor, standing outreach), so a plan
# built from an EMPTY or failed gap model looks complete while carrying zero gap-derived work. Both
# assemble_plan and strategy_view flag that as `degraded` from ONE definition here, so the plan JSON
# and the console's Strategy page can't disagree about whether a strategy is real.
_GAP_CONTENT_KEYS = ("missing_owned_content", "schema_gaps", "thin_corroboration",
                     "surface_actions", "local_seo_gaps", "competitor_defense", "site_technical_gaps")


def _is_degraded(gap: dict) -> bool:
    """True when the gap model produced NO gap-derived content (baseline boilerplate only) -- the
    signal to tell the client 'plan is degraded, re-run the gap model' rather than present setup
    tasks as a finished strategy."""
    return not any((gap or {}).get(k) for k in _GAP_CONTENT_KEYS)


def assemble_plan(business: dict, gap: dict, start: date, strategy: Optional[dict] = None) -> dict:
    # strategy (optional ContentStrategy from content_strategist.plan): when present its cluster
    # campaigns drive the content work orders (a real multi-piece program) instead of the flat
    # 1-per-gap template. Campaign severity is already encoded as earlier cadence weeks, so the
    # within-phase ROI sort below is unchanged.
    wos = build_work_orders(gap, business, strategy=strategy)
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
    # Silent-success guard (see _is_degraded / _GAP_CONTENT_KEYS above): a plan built from an EMPTY or
    # failed gap model looks complete while carrying zero gap-derived work. Detect it from the gap
    # model itself so the console/report can show "plan is degraded -- re-run the gap model".
    gap_derived = [w for w in wos if (w.rationale or {}).get("gap_source", "baseline setup") != "baseline setup"]
    degraded = _is_degraded(gap)
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
        # Whether the Content Strategist actually ran (vs a silent fallback to the deterministic
        # template) -- so a strategist outage isn't invisible on a plan that otherwise looks complete.
        "strategist_used": bool(strategy and strategy.get("campaigns")),
        "work_orders": [w.__dict__ for w in wos],
    }


# ----------------------------------------------------------------------------
# DB + CLI
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Strategy VIEW -- the detailed, per-section plan the console's Strategy page renders.
# This is the "what we'll do and why, in detail" layer: it takes the SAME gap model + work orders
# the plan already produced and organizes them into the three areas the owner asked for
# (AI Visibility / SEO / Search), attaching, per gap, the approach to close it and -- for content
# work -- the concrete spec (title, type, keywords, length, readability, where it publishes,
# objective). No new LLM calls: everything here already exists across the gap model, the work
# orders, and content_generator.piece_brief.
# ----------------------------------------------------------------------------
_SECTION_LABELS = {
    "ai_visibility": "AI Visibility",
    "seo": "SEO (on-site)",
    "search": "Search (rankings)",
}
_SECTION_NARRATIVE = {
    "ai_visibility": "Give the AI assistants accurate, well-corroborated facts to quote about you — "
                     "so they answer buyer questions in your favor instead of a competitor's or a "
                     "stale third-party page's.",
    "seo": "Fix the on-site technical signals (schema, thin/missing pages, crawlability) so both "
           "search engines and AI assistants can cleanly read and trust your facts.",
    "search": "Win the Google searches your buyers actually type — local map-pack and page-1 "
              "rankings — with geo-specific content and a strong Google Business Profile.",
}
_PUBLISH_TO = {
    "local_page": "Your website — local landing page",
    "blog": "Your website — blog",
    "article": "Your website",
    "faq": "Your website — FAQ",
    "white_paper": "Your website — gated resource",
    "landing_page": "Your website — landing page",
    "gbp_post": "Google Business Profile",
    "social_post": "Social media",
    "video_script": "YouTube / social video",
    "bio": "Your website — about/bio",
}
_PLATFORM_PUBLISH = {
    "gbp": "Google Business Profile", "linkedin": "LinkedIn", "facebook": "Facebook",
    "instagram": "Instagram", "x": "X (Twitter)", "youtube": "YouTube", "tiktok": "TikTok",
    "pinterest": "Pinterest", "reddit": "Reddit",
}


def _section_for(gap_source: str | None, capability: str | None, area: str | None) -> str:
    gs, cap, ar = (gap_source or "").lower(), (capability or "").lower(), (area or "").lower()
    if "local search" in gs or cap in ("local_content_creation", "gbp_optimization") or ar == "local":
        return "search"
    if "schema" in gs or "site crawl" in gs or "site technical" in gs or cap in ("schema_markup", "technical_seo"):
        return "seo"
    return "ai_visibility"


def _norm_q(s: str | None) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", _re.sub(r"[^a-z0-9 ]", "", (s or "").lower())).strip()


def _gap_approach_index(gap: dict) -> dict:
    """source_query (normalized) -> {approach, why} pulled from the gap model, so each work-order
    group can show HOW we close its gap (the fix/recommendation) alongside the tasks."""
    idx: dict = {}
    def put(q, approach, why=""):
        k = _norm_q(q)
        if k and k not in idx:
            idx[k] = {"approach": approach or "", "why": why or ""}
    for w in gap.get("weak_queries", []) or []:
        put(w.get("prompt"), w.get("fix"), w.get("problem"))
    for m in gap.get("missing_owned_content", []) or []:
        put(m.get("topic"), m.get("why"), m.get("why"))
    for t in gap.get("thin_corroboration", []) or []:
        put(t.get("claim"), t.get("where_to_get_it"))
    for g in gap.get("local_seo_gaps", []) or []:
        put(g.get("query"), g.get("recommendation"), g.get("why"))
    for g in gap.get("competitor_defense", []) or []:
        put(g.get("query"), g.get("recommendation"), g.get("why"))
    for g in gap.get("site_technical_gaps", []) or []:
        put(g.get("issue"), g.get("recommendation"), g.get("why"))
    return idx


# Capabilities that produce an actual WRITTEN/PRODUCED piece worth a content spec (keywords, length,
# structure). schema_markup is a developer task, not content; local goals fan out to a program (no
# single spec) -- both are excluded so the strategy shows a spec only where a piece is really written.
# The strategy view attaches a content spec for EXACTLY the producible-content capabilities -- the same
# set the Content section shows -- so the plan's "content to produce" and the content page always match.
_SPEC_CAPS = CONTENT_CAPABILITIES

# Rich-media SYNTHESIS pieces (deep-content bundle, podcast, slide deck, research brief,
# explainer-video script) are written FROM the audit + gap model + competitor data + site crawl -- NOT
# from a per-topic source document -- and they carry a generic placeholder topic ("deep content
# bundle", "slide deck", ...) that can never match the corpus. Flagging them "no source material for
# their topic" is therefore a permanent false positive, so they are EXCLUDED from the plan-level
# grounding advisory. (What actually grounds them is business-level fact, surfaced as the "what to
# provide" hint on the REAL content pieces -- not a per-topic doc these synthesis pieces need.)
_SYNTHESIS_CAPS = frozenset({
    "deep_content", "podcast_creation", "slide_deck", "research_brief", "explainer_video",
})


def strategy_view(business_id: int) -> dict:
    """Assemble the detailed strategy the console renders: three sections, each with the gaps it
    covers, the approach to close each, the tasks that do it, and the content specs to produce."""
    try:
        from . import content_generator as _cg
        from . import grounding_coverage as _gc
    except ImportError:  # pragma: no cover
        import content_generator as _cg  # type: ignore
        import grounding_coverage as _gc  # type: ignore
    cov_sigs: list = []   # per-content-piece coverage signals (from piece_brief) -> plan rollup
    ungrounded_pieces: list = []   # enriched "what to provide" entries for genuinely-ungrounded pieces
    with db() as conn:
        gm = conn.execute(
            "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        rows = conn.execute(
            "SELECT id, wo_code, title, capability, instruction, status, area, platform, "
            "target_date, predicted_ai_points, predicted_seo_impact, gap_source, gap_specifics, "
            "why_helps_ai_rep, why_helps_seo, rationale "
            "FROM work_orders WHERE business_id=%s AND NOT COALESCE(superseded, false) "
            "AND status NOT IN ('done','verified','skipped') ORDER BY id", (business_id,)).fetchall()
    gap = {} if not gm else (gm["model"] if isinstance(gm["model"], dict) else json.loads(gm["model"]))
    approach_idx = _gap_approach_index(gap)

    # Group work orders by the gap they close. A Content Strategist CAMPAIGN groups by its campaign_id
    # so its pillar + clusters render as ONE tree; everything else groups by (source_query) when
    # present, else (gap_source|title) -- the prior behavior.
    groups: dict = {}
    order: list = []
    for w in rows:
        w = dict(w)
        gspec = w.get("gap_specifics") if isinstance(w.get("gap_specifics"), dict) else {}
        specs_q = gspec.get("source_query")
        camp_id = gspec.get("campaign_id")
        if camp_id:
            gkey = f"campaign|{camp_id}"
        else:
            gkey = _norm_q(specs_q) or f"{(w.get('gap_source') or '').lower()}|{_norm_q(w.get('title'))}"
        if gkey not in groups:
            if camp_id:
                # A campaign is one coherent content unit -> keep its pillar+clusters in ONE section
                # (local campaigns land in Search, everything else in AI Visibility) so the tree
                # isn't split across sections.
                c_intent = (gspec.get("campaign_intent") or "").lower()
                section = "search" if c_intent == "local" else "ai_visibility"
                groups[gkey] = {"source_query": specs_q, "gap_source": w.get("gap_source"),
                                "section": section, "tasks": [], "specs": [],
                                "campaign": {"id": camp_id, "topic": gspec.get("campaign_topic"),
                                             "intent": c_intent, "funnel_stage": gspec.get("funnel_stage")}}
            else:
                groups[gkey] = {"source_query": specs_q, "gap_source": w.get("gap_source"),
                                "section": _section_for(w.get("gap_source"), w.get("capability"), w.get("area")),
                                "tasks": [], "specs": []}
            order.append(gkey)
        g = groups[gkey]
        rationale = w.get("rationale") if isinstance(w.get("rationale"), dict) else {}
        g["tasks"].append({
            "id": w["id"], "wo_code": w.get("wo_code"), "title": w.get("title"),
            "status": w.get("status"), "capability": w.get("capability"), "area": w.get("area"),
            "platform": w.get("platform"), "instruction": w.get("instruction") or "",
            "target_date": w["target_date"].isoformat() if w.get("target_date") else None,
            "predicted_ai_points": float(w["predicted_ai_points"]) if w.get("predicted_ai_points") is not None else None,
            # role (pillar/cluster/comparison) + cadence week for a campaign piece, so the FE can render
            # the pillar->cluster tree in publish order.
            "role": gspec.get("role"), "publish_week": gspec.get("publish_week"),
            "why": w.get("why_helps_ai_rep") or w.get("why_helps_seo") or rationale.get("why") or "",
        })
        # Content work orders get their concrete production spec (deterministic; no LLM).
        if (w.get("capability") or "") in _SPEC_CAPS:
            try:
                b = _cg.piece_brief(business_id, w)
                pub = _PLATFORM_PUBLISH.get((w.get("platform") or "").lower()) \
                    or _PUBLISH_TO.get(b.get("content_type") or b.get("asset_type") or "", "Your website")
                cov = b.get("coverage")
                # Synthesis pieces carry a generic placeholder topic that can never match the corpus,
                # so their grounding signal is a false positive: don't roll it up into the plan warning
                # and don't show a per-piece "ungrounded" chip for them.
                is_synth = (w.get("capability") or "") in _SYNTHESIS_CAPS
                if isinstance(cov, dict) and not is_synth:
                    cov_sigs.append(cov)
                    # Build the per-piece "what source to provide" entry for BOTH ungrounded (no material)
                    # AND thin (weak material) pieces -- so the "N of M have only thin material" banner
                    # can name which piece + exactly what to upload, not just a bare count. `status` is
                    # tagged so the FE can word it ("provide"/"strengthen").
                    if cov.get("status") in ("ungrounded", "thin"):
                        hint = approach_idx.get(_norm_q(specs_q), {})
                        kws = b.get("keywords") or []
                        ungrounded_pieces.append({
                            "wo_id": w["id"], "title": w.get("title"),
                            "content_type": b.get("content_type") or b.get("asset_type"),
                            "topic": cov.get("topic"), "primary_keyword": b.get("primary_keyword"),
                            "keywords": kws[:4], "status": cov.get("status"),
                            "needed": _gc.needed_material(
                                b.get("content_type") or b.get("asset_type"), cov.get("topic"),
                                kws, hint.get("why") or hint.get("approach")),
                        })
                g["specs"].append({
                    "wo_id": w["id"], "title": w.get("title"),
                    "content_type": b.get("content_type") or b.get("asset_type"),
                    "keywords": b.get("keywords") or [], "primary_keyword": b.get("primary_keyword"),
                    "word_count_target": b.get("word_count_target"),
                    "readability_target": b.get("readability_target"),
                    "structure": b.get("structure"), "publish_to": pub,
                    "objective": w.get("why_helps_ai_rep") or w.get("why_helps_seo") or "",
                    "coverage": (None if is_synth else cov),   # warn-only; suppressed for synthesis pieces
                })
            except Exception as e:  # noqa: BLE001 -- a spec failure must never break the whole view
                log.debug("piece_brief failed for wo %s: %s", w.get("id"), e)

    # Attach the approach/why to each group and bucket into the three sections.
    sections = {k: {"key": k, "label": _SECTION_LABELS[k], "narrative": _SECTION_NARRATIVE[k], "groups": []}
                for k in ("ai_visibility", "seo", "search")}
    _role_rank = {"pillar": 0, "cluster": 1, "comparison": 2, "video": 3}
    for gkey in order:
        g = groups[gkey]
        appr = approach_idx.get(_norm_q(g.get("source_query")), {})
        # The approach ("how we close this") comes from the current gap model when its wording still
        # matches; otherwise fall back to the work order's own stored instruction, which is stable
        # across gap-model regenerations and was itself written from the gap at creation time.
        camp = g.get("campaign")
        if camp:
            # Order a campaign's pieces pillar-first, then clusters by cadence week -- so the tree
            # reads top-down. The campaign's headline is its topic, not a single piece's title.
            g["tasks"].sort(key=lambda t: (_role_rank.get((t.get("role") or "cluster"), 1),
                                           t.get("publish_week") or 99))
            primary = g["tasks"][0] if g["tasks"] else {}
            g["title"] = camp.get("topic") or primary.get("title", "Content campaign")
            g["approach"] = appr.get("approach") or primary.get("instruction", "")
            g["why"] = appr.get("why") or primary.get("why", "")
        else:
            primary = g["tasks"][0] if g["tasks"] else {}
            g["approach"] = appr.get("approach") or primary.get("instruction", "")
            g["why"] = appr.get("why") or primary.get("why", "")
            g["title"] = g.get("source_query") or primary.get("title", "Task")
        sections[g["section"]]["groups"].append(g)
    # Same degraded signal assemble_plan flags: if the gap model carries no gap-derived content, the
    # Strategy page is baseline boilerplate -- tell the client to re-run, don't present it as finished.
    degraded = _is_degraded(gap)
    # Plan-level grounding advisory (warn-only): roll up the per-piece coverage signals piece_brief
    # already computed (SAME scope_query key the draft grounds on -> plan and draft can't disagree).
    # Wrapped: any failure -> coverage=None so GET /strategy always returns.
    try:
        coverage = _gc.plan_coverage(cov_sigs)
        if isinstance(coverage, dict):
            # Per-piece "what to provide" (not just topic names) so the owner knows exactly what
            # source material to add. Only genuinely-ungrounded real content pieces are listed.
            coverage["ungrounded_pieces"] = ungrounded_pieces
    except Exception as e:  # noqa: BLE001
        log.debug("plan_coverage rollup skipped: %s", e)
        coverage = None
    return {
        "summary": gap.get("summary", ""),
        "sections": [sections[k] for k in ("ai_visibility", "seo", "search")],
        "counts": {k: len(sections[k]["groups"]) for k in sections},
        # True when the Content Strategist produced campaigns (vs the deterministic template) -- lets
        # the console show whether the rich program ran or silently fell back.
        "strategist_used": any(g.get("campaign") for k in sections for g in sections[k]["groups"]),
        "degraded": degraded,
        "degraded_reason": (
            "This plan was built from an empty or failed gap analysis, so it shows only standard "
            "setup tasks — not work targeted at your specific gaps. Re-run the gap analysis to "
            "generate a strategy tailored to your business." if degraded else None),
        "coverage": coverage,
    }


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
    # Content Strategist (Phase 1): turn the gap model + keyword/cluster signals + profile into a
    # prioritized content PROGRAM (cluster campaigns) that drives the content work orders. Fail-safe:
    # any failure / disabled / over-budget -> {} and assemble_plan falls back to the deterministic
    # template, so planning never breaks on a strategist outage.
    try:
        from . import content_strategist as _cs
    except ImportError:  # pragma: no cover -- loose-script fallback
        import content_strategist as _cs  # type: ignore
    try:
        strategy = _cs.plan(business_id, gap, business=business) or {}
    except Exception as e:  # noqa: BLE001 -- the strategist must never break planning
        log.warning("content strategist failed (%s); using the deterministic template.", e)
        strategy = {}
    plan = assemble_plan(business, gap, start_date, strategy=strategy)
    # persist
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS strategy_plans ("
            "id BIGSERIAL PRIMARY KEY, business_id BIGINT, plan JSONB, created_at TIMESTAMPTZ DEFAULT now())"
        )
        conn.execute("INSERT INTO strategy_plans (business_id, plan) VALUES (%s,%s)",
                     (business_id, json.dumps(plan)))
        # Persist the ContentStrategy as a first-class object so the strategy view can render the
        # campaign tree and the Phase-4 re-plan loop can diff against it. Inline CREATE mirrors
        # strategy_plans -- no separate migration file needed.
        if strategy.get("campaigns"):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS content_strategies ("
                "id BIGSERIAL PRIMARY KEY, business_id BIGINT, strategy JSONB, "
                "created_at TIMESTAMPTZ DEFAULT now())")
            conn.execute("INSERT INTO content_strategies (business_id, strategy) VALUES (%s,%s)",
                         (business_id, json.dumps(strategy)))
        conn.commit()
    print(json.dumps(plan, indent=2))
    log.info("Plan: %d work orders (%d auto / %d human)%s",
             plan["counts"]["total"], plan["counts"]["auto"], plan["counts"]["human"],
             (f"; strategist: {strategy['counts']['campaigns']} campaigns / "
              f"{strategy['counts']['pieces']} pieces") if strategy.get("campaigns")
             else " (deterministic template)")


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
