"""AI writing assist for drafts: instruction-based Edit-with-AI and one-click Humanize.

Both route through the budget-gated, cost-recorded verified orchestrator
(``agent_tools.llm_text``) -- NEVER a raw provider client -- so the engine's budget +
compliance guarantees hold inside an assisted rewrite (see the CRITICAL INVARIANT in
agent_tools). The model output is then passed through the SAME deterministic policy
scrubs the generator applies (license-number phrasing, negative disambiguation) so an
assisted rewrite can't reintroduce a banned pattern. Neither function auto-saves --
they return the rewritten text and the operator reviews + saves it over the draft.

(The owner asked specifically for "Gemini" here; we deliberately use the verified
orchestrator instead of a raw Gemini call so spend is budget-gated + cost-recorded and
the compliance scrubs run. Adding Gemini as an orchestrator tier is a separate change
that would let this route to Gemini while keeping those guarantees.)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

try:
    from . import agent_tools as _at
    from . import content_generator as _cg
    from . import business_profile as _bp
except ImportError:  # pragma: no cover -- loose-script fallback
    import agent_tools as _at  # type: ignore
    import content_generator as _cg  # type: ignore
    import business_profile as _bp  # type: ignore

log = logging.getLogger("content_assist")


def _tenant_profile(business_id: int) -> Optional[dict]:
    """The tenant's StrategyProfile, fail-safe (-> None on any error). Loaded ONCE per assist call and
    reused for both the prompt-level license policy and the post-rewrite scrub gate."""
    try:
        return _bp.for_business(business_id)
    except Exception:  # noqa: BLE001
        return None


# The hard content-rule tail appended to every assist prompt so the owner's rules survive a rewrite.
# `_policy("")` = the finance-free GENERIC tail (NO_NEGATIVE only); a suppressing tenant splices its
# license/sensitive-ID ban in front. Built per-tenant at the call site from the business's profile.
def _policy(license_policy: str = "") -> str:
    return license_policy + _at.NO_NEGATIVE_DISAMBIGUATION_POLICY


_POLICY = _policy()   # finance-free GENERIC alias (kept for back-compat / import-time references)

_HUMANIZE_BASE = (
    "You are a seasoned human editor. Rewrite the article below so it reads like a real, "
    "experienced person wrote it: natural rhythm, varied sentence length, concrete specifics, "
    "and a warm, credible voice. Do NOT change its meaning, facts, numbers, structure, headings, "
    "lists, links, or markdown. Strip the AI tells -- formulaic transitions, hedging, repetitive "
    "phrasing, empty intensifiers, and cliches like 'in today's world', 'when it comes to', "
    "'it's important to note', 'in conclusion'. Do NOT add any new facts, claims, statistics, "
    "names, or credentials. Keep every heading, list, link, disclaimer, byline, and 'Last updated' "
    "line, and keep the original language. Output ONLY the rewritten article in markdown -- no "
    "preamble, no commentary."
)


def _humanize_system(license_policy: str = "") -> str:
    return _HUMANIZE_BASE + _policy(license_policy)


HUMANIZE_SYSTEM = _humanize_system()   # finance-free GENERIC alias; per-tenant built at the call site

_EDIT_BASE = (
    "You are a senior content editor making ONE specific revision an operator asked for. Apply "
    "ONLY the requested change to the article below and preserve everything else: meaning, facts, "
    "headings, lists, links, markdown, byline, and disclaimers. Do NOT invent facts, statistics, "
    "credentials, dates, or names. If the instruction would require information you do not have, "
    "leave a clearly-marked [INSERT: what's needed] placeholder instead of fabricating it. Output "
    "ONLY the full revised article in markdown -- no preamble, no commentary."
)


def _edit_system(license_policy: str = "") -> str:
    return _EDIT_BASE + _policy(license_policy)


EDIT_SYSTEM = _edit_system()   # finance-free GENERIC alias; per-tenant built at the call site

# Long-form drafts (white papers, pillar pages) can run several thousand words; the seam's default
# 2000-token cap would truncate the rewrite mid-article (silent no-op / lost tail), so lift it.
_MAX_TOKENS = 8000


def _scrub_policy(out: str, profile: Optional[dict] = None) -> str:
    """Run the generator's deterministic policy scrubs on assisted output. The license-number scrub is
    gated on the tenant's profile (a generic tenant may keep license numbers; a regulated-finance tenant
    has them scrubbed) -- profile None means run it (fail-safe). We intentionally do NOT strip
    [INSERT: ...] placeholders here -- an assist result is still a draft, and those markers are the
    pre-publish checklist the reviewer needs to see (approval already blocks on them)."""
    out = _cg._scrub_license_phrasing(out or "", profile)
    out = _cg._scrub_negative_disambiguation(out)
    return out.strip()


def humanize(business_id: int, body: str) -> dict:
    """Rewrite a draft body to read more human, preserving meaning/facts/structure. Returns
    {ok, rewritten_text} (operator decides whether to save it). Never raises on a model miss."""
    body = (body or "").strip()
    if not body:
        return {"ok": False, "error": "This draft has no body to rewrite."}
    profile = _tenant_profile(business_id)
    try:
        out = _at.llm_text(_humanize_system(_bp.license_policy_for(profile)), body,
                           business_id=business_id, tier="mid",
                           max_tokens=_MAX_TOKENS, operation="humanize")
    except _at.BudgetExceededError:
        return {"ok": False, "error": "Over the monthly budget — raise the cap to use AI assist."}
    out = _scrub_policy(out, profile)
    if not out:
        return {"ok": False, "error": "The rewrite is unavailable right now — try again."}
    return {"ok": True, "rewritten_text": out}


def ai_edit(business_id: int, body: str, instruction: str) -> dict:
    """Apply an operator's specific edit instruction to a draft body via the LLM. Returns
    {ok, rewritten_text} (operator decides whether to save it). Never raises on a model miss."""
    body = (body or "").strip()
    instruction = (instruction or "").strip()
    if not body:
        return {"ok": False, "error": "This draft has no body to edit."}
    if not instruction:
        return {"ok": False, "error": "Describe the change you want."}
    # The instruction comes from the authenticated editor (trusted); the body is our own content.
    user = f"INSTRUCTION:\n{instruction}\n\n---\nARTICLE:\n{body}"
    profile = _tenant_profile(business_id)
    try:
        out = _at.llm_text(_edit_system(_bp.license_policy_for(profile)), user,
                           business_id=business_id, tier="full",
                           max_tokens=_MAX_TOKENS, operation="ai_edit")
    except _at.BudgetExceededError:
        return {"ok": False, "error": "Over the monthly budget — raise the cap to use AI assist."}
    out = _scrub_policy(out, profile)
    if not out:
        return {"ok": False, "error": "The edit is unavailable right now — try again."}
    return {"ok": True, "rewritten_text": out}


# ---------------------------------------------------------------------------
# Prompt enhancement: turn the operator's short "describe what you want" into an
# optimized production brief for the chosen content type, grounded in the brand's
# identity + source material. Runs through the SAME verified orchestrator (budget-
# gated, cost-recorded) as the assist functions above. Returns a brief the operator
# reviews/edits before generating -- it never generates anything itself.
# ---------------------------------------------------------------------------
# Content types that are produced as SPOKEN video (HeyGen). These get the faithful,
# verbatim-safe video-script brief; everything else gets the web-article brief.
_VIDEO_TYPES = {"video", "explainer_video", "video_script", "short_video", "reel", "shorts"}

_ENHANCE_ARTICLE_BASE = (
    "You are a senior content strategist writing a PRODUCTION BRIEF for ONE web article. The operator "
    "gave a short description of what they want. Rewrite it into a single, information-dense brief the "
    "content generator can execute -- written as instructions, NOT as the article itself. Cover, "
    "compactly: the working title and angle; the target search intent and 4-8 primary/secondary "
    "keywords to work in; the section outline (the H2/H3 headings a reader and an AI answer engine both "
    "need); an appropriate target word count for the topic; how many images/visuals and roughly where "
    "they go; and the AEO/GEO/SEO targets to hit (a direct-answer opening, cited statistics, quotable "
    "expert lines, and schema-friendly structure). Keep it a tight brief, not an essay. Do NOT write "
    "the article. Do NOT invent facts, statistics, credentials, dates, or names -- describe what to "
    "include and mark [INSERT: what's needed] where the writer must supply a real fact. Output ONLY "
    "the brief as markdown."
)

_ENHANCE_VIDEO_BASE = (
    "You are a video producer writing a PRODUCTION BRIEF for a short, brand-safe explainer VIDEO that "
    "will be produced by an AI avatar tool (HeyGen). The operator gave a short description. Rewrite it "
    "into a brief the script generator can execute: the video's single goal and the question/search it "
    "answers; the on-screen title; a suggested spoken structure (hook -> 2-4 key points -> call to "
    "action) with an approximate runtime and word budget for a ~60-120 second clip; the tone and "
    "framing; and the on-screen text/callouts. Ground every claim in the brand's own facts and source "
    "material provided below. This brief becomes a script that a compliance-reviewed avatar will speak "
    "VERBATIM, so keep it faithful and free of unverifiable claims: do NOT invent statistics, "
    "credentials, disclaimers, or names -- mark [INSERT: what's needed] where a real fact is required. "
    "Output ONLY the brief as markdown."
)

_ENHANCE_MAX_TOKENS = 1500


def _grounding_context(business_id: int) -> str:
    """Compact brand grounding for prompt enhancement: business identity + brand writing guardrails +
    the titles of the owner's source material, so the enhanced brief is anchored to real facts. Fail-
    safe -- returns whatever is available and never raises."""
    parts: list[str] = []
    try:
        from .db import db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    try:
        with db() as conn:
            b = conn.execute("SELECT name, geo, services, goal FROM businesses WHERE id=%s",
                             (business_id,)).fetchone()
        if b:
            ident = {k: b.get(k) for k in ("name", "geo", "services", "goal") if b.get(k)}
            if ident:
                parts.append("BUSINESS: " + "; ".join(f"{k}: {v}" for k, v in ident.items()))
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import source_material as _sm
    except ImportError:  # pragma: no cover
        try:
            import source_material as _sm  # type: ignore
        except Exception:  # noqa: BLE001
            _sm = None  # type: ignore
    if _sm is not None:
        try:
            g = _sm.guardrails(business_id)
            if g:
                parts.append("BRAND WRITING RULES: " + (g if isinstance(g, str) else json.dumps(g, default=str))[:800])
        except Exception:  # noqa: BLE001
            pass
        try:
            docs = _sm.list_documents(business_id) or []
            titles = [d.get("title") for d in docs if isinstance(d, dict) and d.get("title")][:12]
            if titles:
                parts.append("SOURCE MATERIAL ON FILE (titles): " + "; ".join(titles))
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(parts)


def enhance_prompt(business_id: int, description: str, content_type: str) -> dict:
    """Rewrite the operator's free-text 'describe what you want' into an optimized production brief
    for the selected content type, grounded in the brand's identity + source material. A VIDEO type
    targets the HeyGen script brief (faithful, verbatim-safe); everything else targets a web-article
    brief (layout, keywords, word count, images, AEO/SEO targets). Returns {ok, enhanced_prompt}.
    Never raises on a model miss."""
    description = (description or "").strip()
    if not description:
        return {"ok": False, "error": "Describe what you want first, then enhance it."}
    is_video = (content_type or "").strip().lower() in _VIDEO_TYPES
    profile = _tenant_profile(business_id)
    system = (_ENHANCE_VIDEO_BASE if is_video else _ENHANCE_ARTICLE_BASE) + _policy(_bp.license_policy_for(profile))
    grounding = _grounding_context(business_id)
    user = (f"CONTENT TYPE: {content_type}\n\nWHAT THE OPERATOR WANTS:\n{description}"
            + (f"\n\n---\nBRAND GROUNDING (anchor the brief to these real facts):\n{grounding}"
               if grounding else ""))
    try:
        out = _at.llm_text(system, user, business_id=business_id, tier="mid",
                           max_tokens=_ENHANCE_MAX_TOKENS, operation="enhance_prompt")
    except _at.BudgetExceededError:
        return {"ok": False, "error": "Over the monthly budget — raise the cap to use AI assist."}
    out = (out or "").strip()
    if not out:
        return {"ok": False, "error": "Enhancement is unavailable right now — try again."}
    return {"ok": True, "enhanced_prompt": out}
