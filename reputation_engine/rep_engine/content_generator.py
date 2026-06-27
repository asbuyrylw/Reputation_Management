"""
Reputation Crowding-Out Engine -- Module 6: AI Content Generator
================================================================
Closes the loop from gap -> finished DRAFT artifact. For each content-type work
order in the plan, it generates the actual asset (FAQ, schema JSON-LD, article,
bio, GBP post, review-request copy), scores it against a quality rubric, auto-
revises if it falls short, runs a compliance screen, and stores it as a
`pending_review` draft. NOTHING is auto-published.

Design principles (from the roadmap):
  - AI generates, HUMAN approves, system tracks. Auto-drafting removes ~80% of the
    labor while keeping the human gate -- essential for regulated (financial) clients.
  - Win-Gate-style self-evaluation: generate -> score against rubric -> auto-revise
    if below threshold -> re-score (bounded passes).
  - Compliance gate as a first-class step: disclosures present, no performance
    promises, broker-dealer relationship disclosed where relevant.
  - pgvector-ready: a hook to skip generation when equivalent content already
    exists (no-op until pgvector is wired).

Run:
    python -m rep_engine.content_generator generate --business-id 1            # all auto content WOs
    python -m rep_engine.content_generator generate --business-id 1 --wo 12    # one work order
    python -m rep_engine.content_generator list --business-id 1                # show drafts + status
    python -m rep_engine.content_generator approve --draft 5 --reviewer "Logan"
    python -m rep_engine.content_generator reject  --draft 5 --reviewer "Logan" --notes "off-brand"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from typing import Optional


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
from pydantic import ValidationError

try:
    from . import ai_state_audit as llm   # reuse the orchestrator LLM plumbing
    from .llm_schemas import ComplianceResult, EvalResult
except ImportError:  # pragma: no cover
    import ai_state_audit as llm  # type: ignore
    from llm_schemas import ComplianceResult, EvalResult  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("content_generator")


QUALITY_THRESHOLD = float(os.getenv("CONTENT_QUALITY_THRESHOLD", "0.75"))   # PH 2
# Minimum citation-readiness (0-100, "will an AI quote this?") for a draft to pass as ready rather
# than going back for a fix. Was advisory-only; now an enforced gate (Phase D).
CITATION_READY_MIN = float(os.getenv("CONTENT_CITATION_READY_MIN", "55"))
MAX_REVISIONS = int(os.getenv("CONTENT_MAX_REVISIONS", "2"))                # PH 3

# Capabilities that this module knows how to generate (others stay manual).
GENERATABLE = {
    "content_writing": "article",
    "schema_markup": "schema",
    "review_generation": "review_request",
}
# asset_type inferred from work-order title keywords as a fallback
TITLE_HINTS = [
    ("faq", "faq"), ("schema", "schema"), ("bio", "bio"),
    ("article", "article"), ("post", "gbp_post"), ("review", "review_request"),
]




def _ensure_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_drafts (
                id BIGSERIAL PRIMARY KEY, business_id BIGINT, work_order_id BIGINT,
                asset_type TEXT, title TEXT, body TEXT, target_query TEXT,
                quality_score NUMERIC(4,2), quality_notes JSONB DEFAULT '{}'::jsonb,
                revision_count INT DEFAULT 0, compliance_pass BOOLEAN,
                compliance_flags JSONB DEFAULT '[]'::jsonb,
                status TEXT DEFAULT 'pending_review', reviewer TEXT, reviewed_at TIMESTAMPTZ,
                published_asset_id BIGINT, created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now())
        """)
        conn.commit()


# ----------------------------------------------------------------------------
# pgvector hook (no-op until wired) -- would prevent regenerating existing content
# ----------------------------------------------------------------------------
def _already_covered(business_id: int, topic: str) -> bool:
    """Placeholder for the pgvector semantic-dedup check. Returns False (always
    generate) until pgvector memory is wired in -- a future enhancement (the
    pgvector extension may not be installed). PH 4."""
    return False


# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------
GEN_SYSTEM = (
    "You are an expert content writer AND answer-engine-optimization (AEO/GEO) + SEO strategist for "
    "a reputation program that publishes ACCURATE, helpful, well-structured content so it becomes "
    "what AI assistants (ChatGPT, Perplexity, Gemini, Google AI Overview) and Google surface about a "
    "business. GROUND every claim in the REAL facts provided (the business's crawled website + "
    "profile); prefer those facts over placeholders. Only use a clearly-labeled [INSERT: ...] "
    "placeholder for a specific fact that is genuinely NOT provided. "
    "STRUCTURE FOR AI CITATION (this is what gets the content quoted by answer engines): "
    "(1) open with a crisp 40-60 word DIRECT ANSWER to the core question (front-load the key fact -- "
    "most AI citations come from the top of the page); (2) use clear H2/H3 headings phrased as the "
    "questions a reader would ask; (3) include a short FAQ / Q&A section near the end; (4) give one "
    "quotable, attributable statistic or definitive sentence per section; (5) name the business + "
    "city + service explicitly and consistently (entity clarity); (6) where an image strengthens the "
    "page, insert a markdown image with DESCRIPTIVE alt text as ![alt describing the image](IMAGE: "
    "short generation prompt) so a hero/explainer image + alt text can be produced; (7) add a visible "
    "'Last updated: [INSERT: month year]' line for freshness. "
    "Naturally weave in the target search keywords where they fit (never keyword-stuff). Directly "
    "address the gap / narrative the content is meant to fix. Never fabricate facts, credentials, "
    "reviews, or statistics. Write in a warm, trustworthy, plain tone. Output ONLY the asset "
    "content -- no preamble."
)


def _grounding_context(business_id: int) -> dict:
    """Pull the REAL grounding for content generation, so the writer works from facts and the
    right language instead of generic filler:
      - site_facts: what the business's own website actually says (latest crawl summary),
      - gap_focus:  what AI currently gets wrong / the narrative this content must close,
      - keywords:   the SEO keywords this piece should rank for (the real target_keywords set
                    populated by the keyword-intelligence layer / `keyword_research` job).
    Everything is best-effort: missing data degrades to an empty section, never an error."""
    site_facts = gap_focus = ""
    keywords: list = []
    try:
        with db() as conn:
            sa = conn.execute(
                "SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,)).fetchone()
            if sa and sa["summary"]:
                s = sa["summary"] if isinstance(sa["summary"], (dict, list)) else json.loads(sa["summary"])
                site_facts = json.dumps(s, default=str)[:3500]
            gm = conn.execute(
                "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,)).fetchone()
            if gm and gm["model"]:
                m = gm["model"] if isinstance(gm["model"], (dict, list)) else json.loads(gm["model"])
                gap_focus = json.dumps(m, default=str)[:2800]
    except Exception as e:  # noqa: BLE001 -- grounding is best-effort; never block generation
        log.debug("site/gap grounding unavailable: %s", e)
    # Real target_keywords read (populated by the keyword_research job). Its own connection so a
    # missing table / empty set can't poison the site+gap reads above. Top ~15 by priority so the
    # generator weaves in the highest-value REAL terms, not generic filler.
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT keyword, kind, intent, priority FROM target_keywords WHERE business_id=%s "
                "ORDER BY priority DESC NULLS LAST, keyword LIMIT 15", (business_id,)).fetchall()
            keywords = [{"keyword": r["keyword"], "kind": r.get("kind"),
                         "intent": r.get("intent"), "priority": r.get("priority")} for r in rows]
    except Exception:  # noqa: BLE001 -- best-effort: missing table or empty result degrades to no keywords
        keywords = []
    return {"site_facts": site_facts, "gap_focus": gap_focus, "keywords": keywords}


def _asset_type_for(wo: dict) -> Optional[str]:
    cap = (wo.get("capability") or "").lower()
    if cap in GENERATABLE:
        # refine via title
        title = (wo.get("title") or "").lower()
        for kw, t in TITLE_HINTS:
            if kw in title:
                return t
        return GENERATABLE[cap]
    # fallback: infer from title only
    title = (wo.get("title") or "").lower()
    for kw, t in TITLE_HINTS:
        if kw in title:
            return t
    return None


def _brand_voice(business_id: int) -> str:
    """A short sample of the brand's own APPROVED writing, so new content matches the voice
    they've already signed off on. Empty until something has been approved."""
    try:
        with db() as conn:
            r = conn.execute(
                "SELECT body FROM content_drafts WHERE business_id=%s AND status='approved' "
                "AND body IS NOT NULL AND length(body) > 120 ORDER BY id DESC LIMIT 1",
                (business_id,)).fetchone()
        if r and r["body"]:
            return str(r["body"])[:1200]
    except Exception:  # noqa: BLE001 -- voice is best-effort
        pass
    return ""


_OUTLINE_SYSTEM = (
    "You are an SEO content strategist. Produce a TIGHT outline for the asset: an H1 plus 4-7 H2 "
    "section headings, each with a one-line note on what it covers. MAP the target keywords and "
    "the gap-to-close onto specific sections. Plain-text outline only -- no preamble, no prose."
)


def _outline(biz: dict, wo: dict, asset_type: str, grounding: dict) -> str:
    """Pass 1 of the multi-pass pipeline (long-form only): a keyword-mapped outline the draft
    pass then writes from, so structure + keyword coverage are planned, not accidental."""
    prompt = _gen_prompt(biz, wo, asset_type, grounding) + "\n\nProduce ONLY the outline."
    return (llm.orchestrator_text(_OUTLINE_SYSTEM, prompt, max_tokens=700, tier="mid") or "").strip()


def _keyword_coverage(body: str, grounding: dict) -> dict:
    """Deterministic SEO self-check: which target keywords does the draft actually contain?
    A keyword counts as covered if it appears verbatim OR all of its significant words appear.
    `important_missing` (primary/local) is what we force one revision pass to fix."""
    kws = grounding.get("keywords") or []
    text = (body or "").lower()
    covered, missing, important_missing = [], [], []
    for k in kws:
        kw = (k.get("keyword") or "").strip()
        if not kw:
            continue
        words = [w for w in re.findall(r"[a-z0-9]+", kw.lower()) if len(w) > 2]
        present = kw.lower() in text or (bool(words) and all(w in text for w in words))
        if present:
            covered.append(kw)
        else:
            missing.append(kw)
            if k.get("kind") in ("primary", "local"):
                important_missing.append(kw)
    total = len(covered) + len(missing)
    return {"covered": covered, "missing": missing, "important_missing": important_missing,
            "rate": round(len(covered) / total, 2) if total else None}


def _gen_prompt(biz: dict, wo: dict, asset_type: str, grounding: Optional[dict] = None,
                outline: str = "", voice: str = "") -> str:
    grounding = grounding or {"site_facts": "", "gap_focus": "", "keywords": []}
    name = biz.get("name", "the business")
    geo = biz.get("geo", "")
    svc = biz.get("services", "")
    industry = biz.get("industry", "")
    goal = biz.get("goal", "")
    contested = biz.get("contested_terms", "")
    instr = wo.get("instruction", "")
    title = wo.get("title", "")
    specs = {
        "faq": "Write an FAQ page (6-10 Q&A pairs) in markdown that directly answers "
               "the real questions people ask about this business.",
        "schema": "Output ONLY valid JSON-LD schema markup (no prose) appropriate to the "
                  "page -- choose from Organization, LocalBusiness, FAQPage, Person, Review. "
                  "Populate it with the REAL business facts provided above.",
        "article": "Write a 600-900 word helpful, locally-relevant article in markdown with a "
                   "clear H1 and subheadings, answering the target question accurately and "
                   "working in the target keywords naturally.",
        "bio": "Write a professional bio page in markdown (250-400 words) establishing "
               "authority and trust, grounded in the real facts above.",
        "gbp_post": "Write a short Google Business Profile post (80-150 words), friendly and "
                    "local, naturally including a local keyword.",
        "review_request": "Write a short, warm review-request message (SMS + email versions) "
                          "asking a happy client to leave a Google review, with a placeholder for the link.",
    }
    spec = specs.get(asset_type, "Write the requested asset in markdown.")
    kw = grounding.get("keywords") or []
    kw_line = ""
    if kw:
        kw_line = ("Target search keywords to weave in NATURALLY (do not keyword-stuff): "
                   + ", ".join(str(k.get("keyword")) for k in kw if k.get("keyword")) + "\n")
    parts = [
        f"Business: {name}",
        f"Industry: {industry}" if industry else "",
        f"Location / areas served: {geo}" if geo else "",
        f"Services: {svc}" if svc else "",
        f"Positioning goal (what AI + customers should understand): {goal}" if goal else "",
        f"Narratives working against them (counter, don't repeat): {contested}" if contested else "",
        "",
        "REAL FACTS FROM THE BUSINESS'S OWN WEBSITE (from our crawl) — ground your writing in "
        "these and do not contradict them:",
        grounding.get("site_facts") or "(no site crawl available — use [INSERT: ...] for unknown facts)",
        "",
        "WHAT AI CURRENTLY GETS WRONG / THE GAP THIS CONTENT MUST CLOSE:",
        grounding.get("gap_focus") or "(general trust & visibility)",
        "",
        f"Work order: {title}",
        f"Instruction: {instr}" if instr else "",
        kw_line + f"Target question this should answer when someone asks AI: "
        f"{wo.get('target_query','(general trust/visibility)')}",
        "",
        ("FOLLOW THIS OUTLINE (it maps the keywords + gap to sections):\n" + outline) if outline else "",
        ("MATCH THIS BRAND VOICE (a sample of their approved writing — tone/cadence only, do not "
         "copy facts):\n\"\"\"\n" + voice + "\n\"\"\"") if voice else "",
        "",
        f"Task: {spec}",
    ]
    return "\n".join(p for p in parts if p != "")


# Marquee long-form assets get the best model; short/structured assets stay on the mid tier.
_ASSET_TIER = {"article": "full", "faq": "full", "bio": "full"}


def _generate_one(biz: dict, wo: dict, asset_type: str, grounding: Optional[dict] = None,
                  outline: str = "", voice: str = "") -> str:
    tier = _ASSET_TIER.get(asset_type, "mid")
    return llm.orchestrator_text(GEN_SYSTEM,
                                 _gen_prompt(biz, wo, asset_type, grounding, outline=outline, voice=voice),
                                 max_tokens=2600, tier=tier)


# ----------------------------------------------------------------------------
# Self-evaluation (Win-Gate-style) + auto-revision
# ----------------------------------------------------------------------------
EVAL_SYSTEM = (
    "You are a strict content QA reviewer. Score the draft against this rubric and "
    "return STRICT JSON only: {\"score\": 0.0-1.0, \"accuracy\": bool (no fabricated "
    "facts/reviews/stats), \"answers_query\": bool, \"structure\": bool (clear headings/"
    "format for the asset type), \"tone\": bool (warm, trustworthy, not salesy), "
    "\"issues\": [strings], \"fixes\": [concise actionable fixes]}. Be hard on "
    "fabrication: any invented specific fact, statistic, credential, or review caps "
    "score at 0.4."
)


def _evaluate(asset_type: str, target_query: str, body: str) -> dict:
    user = json.dumps({"asset_type": asset_type, "target_query": target_query, "draft": body})
    # rubric scoring is classification/QA -> cheap tier (Haiku/gpt-4o-mini).
    res = llm.orchestrator_json(EVAL_SYSTEM, user, tier="cheap")
    if not res:
        return {}
    try:
        # Garbled/out-of-range eval JSON is 'could not evaluate', NOT a real score of 0.
        return EvalResult.model_validate(res).model_dump()
    except ValidationError as e:
        log.warning("_evaluate: eval JSON failed validation (treating as unscored): %s",
                    str(e).splitlines()[0] if str(e) else e)
        return {}


REVISE_SYSTEM = (
    "You are revising a content draft to fix the listed issues while keeping what "
    "works. Do not introduce fabricated facts -- use [INSERT: ...] placeholders "
    "instead. Output ONLY the revised asset content, no preamble."
)


def _revise(body: str, fixes: list) -> str:
    user = "Issues/fixes to address:\n- " + "\n- ".join(fixes or []) + f"\n\nCurrent draft:\n{body}"
    # creative rewrite -> mid tier (Sonnet/gpt-4o).
    return llm.orchestrator_text(REVISE_SYSTEM, user, max_tokens=2200, tier="mid")


# ----------------------------------------------------------------------------
# Compliance gate (first-class)
# ----------------------------------------------------------------------------
COMPLIANCE_SYSTEM = (
    "You are a financial-services marketing compliance screener. Review the content "
    "and return STRICT JSON only: {\"pass\": bool, \"flags\": [strings]}. Flag any of: "
    "guaranteed/implied investment returns or performance promises; claims that imply "
    "the brand is an independent registered firm when it may be a representative of a "
    "broker-dealer; missing required disclosure of the broker-dealer relationship where "
    "the content markets financial products; unverifiable superlatives ('best', "
    "'#1') stated as fact; testimonials presented without context. If the content is "
    "non-financial or purely informational, pass it unless it makes false claims."
)

# Firm-type-specific guidance so the screen demands the RIGHT disclosures (or none) per tenant,
# instead of always assuming a broker-dealer-affiliated firm.
_FIRM_TYPE_RULES = {
    "ria": ("This business is a Registered Investment Adviser (RIA), held to the SEC/state "
            "Marketing Rule. Require fiduciary-consistent language; flag performance/return "
            "promises and testimonials lacking the required disclosures; do NOT demand a "
            "broker-dealer relationship disclosure (an RIA is not a BD)."),
    "broker_dealer": ("This business is or represents a broker-dealer (FINRA Rule 2210). Require "
                      "the broker-dealer relationship disclosure where financial products are "
                      "marketed; flag performance promises and unbalanced testimonials."),
    "insurance": ("This business is an insurance agency. Flag guaranteed-return/risk-free language "
                  "on insurance/annuity products and require suitability-consistent framing; a "
                  "broker-dealer disclosure is generally NOT required."),
    "non_financial": ("This business is NON-FINANCIAL. Do NOT require any financial/broker-dealer "
                      "disclosures. Only flag genuinely false or misleading claims."),
}


def _reg_profile(business_id: int) -> dict:
    try:
        with db() as conn:
            r = conn.execute("SELECT regulatory_profile FROM businesses WHERE id=%s", (business_id,)).fetchone()
        rp = r["regulatory_profile"] if r else None
        return rp if isinstance(rp, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _compliance_system(reg: dict | None) -> str:
    """Adapt the base compliance prompt to the tenant's firm type + required disclosures."""
    if not reg:
        return COMPLIANCE_SYSTEM
    extra = []
    ft = (reg.get("firm_type") or "").lower()
    if ft in _FIRM_TYPE_RULES:
        extra.append(_FIRM_TYPE_RULES[ft])
    disc = reg.get("disclosures") or []
    if disc:
        extra.append("Required disclosures for this business: " + "; ".join(str(d) for d in disc) + ".")
    return COMPLIANCE_SYSTEM + ("\n\n" + "\n".join(extra) if extra else "")


# Hard financial-marketing prohibitions, matched deterministically. Unlike the LLM
# screen these cannot be talked out of their verdict by a hostile/garbled draft, so
# a hit here is AUTHORITATIVE: the content is non-compliant regardless of the LLM.
_COMPLIANCE_RULES: list[tuple[str, str]] = [
    (r"\bguarantee[ds]?\b[^.\n]{0,40}\b(returns?|profits?|income|results?|gains?|growth)\b",
     "implies guaranteed returns/results"),
    (r"\b(risk[-\s]?free|no[-\s]?risk|zero[-\s]?risk)\b", "claims risk-free"),
    (r"\b(?:#\s?1|number[-\s]one|the\sbest|best[-\s]in[-\s]class)\b",
     "unverifiable superlative (#1 / best)"),
    (r"\b\d{1,3}\s?%[^.\n]{0,30}\b(guaranteed|returns?|profits?|gains?)\b",
     "specific performance promise"),
]
_COMPLIANCE_PATTERNS = [(re.compile(p, re.I), msg) for p, msg in _COMPLIANCE_RULES]


def _deterministic_compliance(body: str) -> list[str]:
    """Non-LLM, non-prompt-injectable screen for hard financial-marketing rules.
    Returns the list of triggered-rule descriptions (empty == nothing tripped)."""
    text = body or ""
    return [msg for pat, msg in _COMPLIANCE_PATTERNS if pat.search(text)]


def _compliance(body: str, system: Optional[str] = None, *, is_reply: bool = False) -> dict:
    # Deterministic, non-injectable screen first -- its verdict is authoritative.
    det_flags = _deterministic_compliance(body)
    # Reply paths (review/mention brand replies) carry FTC/ToS risk the generic financial screen
    # misses (it passes anything "non-financial"). Run the deterministic reply screen on every
    # reply and use the reply-aware LLM prompt so a reply is never rubber-stamped as non-financial.
    if is_reply:
        try:
            from . import reply_compliance as _rc
        except ImportError:  # pragma: no cover -- loose-script fallback
            import reply_compliance as _rc  # type: ignore
        det_flags = det_flags + _rc.screen(body)
        if system is None:
            system = _rc.REPLY_COMPLIANCE_SYSTEM
    # compliance screen is classification -> cheap tier (Haiku/gpt-4o-mini). `system` is the
    # firm-type-adapted prompt (falls back to the generic financial screen).
    res = llm.orchestrator_json(system or COMPLIANCE_SYSTEM, json.dumps({"content": body}), tier="cheap")
    # default-safe: if the screener couldn't run (no keys), mark unknown -> needs
    # human; but if the deterministic rules tripped, FAIL CLOSED regardless of LLM.
    if not res:
        if det_flags:
            return {"pass": False,
                    "flags": det_flags + ["compliance screener unavailable -- deterministic rules tripped"]}
        return {"pass": None, "flags": ["compliance screener unavailable (no LLM) -- human must review"]}
    try:
        validated = ComplianceResult.model_validate(res)
    except ValidationError as e:
        # A garbled compliance response is 'unknown', NOT an auto-pass and NOT an auto-fail.
        log.warning("_compliance: screen JSON failed validation (routing to human): %s",
                    str(e).splitlines()[0] if str(e) else e)
        return {"pass": None,
                "flags": det_flags + ["compliance screen returned malformed output -- human must review"]}
    # by_alias=True restores the literal 'pass' key the DB column + callers expect.
    result = validated.model_dump(by_alias=True)
    # Deterministic rules are authoritative and cannot be prompt-injected: if they
    # trip, the content is NOT compliant no matter what the LLM verdict claimed.
    if det_flags:
        result["pass"] = False
        result["flags"] = list(result.get("flags", [])) + det_flags
    return result


def draft_reply(system: str, payload: dict, *, max_tokens: int = 400,
                fallback: Optional[str] = None) -> Optional[str]:
    """Shared fenced-LLM drafter for brand replies (GBP reviews + owned mentions).

    `payload` carries the reply context (the caller is responsible for `_fence_untrusted`-ing
    any externally-sourced fields -- author/title/body -- before passing them in). Returns the
    drafted reply text, or `fallback` if the model is unavailable/empty. The result is NOT
    compliance-screened here; the caller runs `_compliance(draft, is_reply=True)`."""
    txt = llm.orchestrator_text(system, json.dumps(payload), max_tokens=max_tokens, tier="mid")
    txt = (txt or "").strip()
    return txt or fallback


# ----------------------------------------------------------------------------
# Placeholder extraction + compliance auto-fix
# ----------------------------------------------------------------------------
_PLACEHOLDER_RE = re.compile(r"\[INSERT:[^\]]*\]", re.I)


def _extract_placeholders(body: str) -> list[str]:
    """Pull every [INSERT: ...] marker out of a draft. These are facts the AI didn't have
    (a license number, a contact email) that a human must fill in before publishing -- the
    UI shows them as a red pre-publish checklist and approval is blocked until they're gone."""
    seen, out = set(), []
    for m in _PLACEHOLDER_RE.findall(body or ""):
        key = m.lower()
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


COMPLIANCE_FIX_SYSTEM = (
    "You are a financial-services compliance editor. Revise the content to RESOLVE the listed "
    "compliance issues while preserving the accurate, helpful message. REMOVE prohibited claims "
    "(guaranteed/implied returns, performance promises, 'risk-free', unverifiable superlatives "
    "like 'best'/'#1' stated as fact). ADD any missing required disclosures -- e.g. the "
    "broker-dealer / representative relationship where financial products are marketed, and that "
    "any testimonials are individual experiences and not typical results. Do NOT fabricate facts: "
    "use a [INSERT: ...] placeholder for any specific detail you don't have (a license number, an "
    "affiliated firm name). Output ONLY the revised content, no preamble."
)


def _compliance_autofix(biz: dict, body: str, flags: list, reg: Optional[dict] = None) -> Optional[str]:
    """Attempt to make a flagged draft compliant: strip prohibited claims + insert the missing
    disclosures (using what we know about the business + its regulatory profile). Returns the
    revised body, or None. The caller re-screens the result -- this never decides compliance."""
    reg = reg or {}
    ft = (reg.get("firm_type") or "").lower()
    disc = reg.get("disclosures") or []
    reg_line = ""
    if ft:
        reg_line = f"Firm type: {ft}. "
        if ft == "non_financial":
            reg_line += "Do NOT add any financial/broker-dealer disclosures. "
    if disc:
        reg_line += "Use ONLY these required disclosures (verbatim where possible): " + "; ".join(str(d) for d in disc) + ". "
    ctx = (
        f"Business: {biz.get('name', '')} -- services: {biz.get('services', '')}.\n"
        f"{reg_line}\n"
        f"Narratives working against them (context only): {biz.get('contested_terms', '')}.\n"
        "Compliance issues to resolve:\n- " + "\n- ".join(str(f) for f in (flags or []))
        + f"\n\nContent to revise:\n{body}"
    )
    revised = llm.orchestrator_text(COMPLIANCE_FIX_SYSTEM, ctx, max_tokens=2400, tier="mid")
    return (revised or "").strip() or None


# ----------------------------------------------------------------------------
# Orchestrated generation for a work order
# ----------------------------------------------------------------------------
def generate_for_wo(business_id: int, wo: dict, biz: dict) -> Optional[int]:
    asset_type = _asset_type_for(wo)
    if not asset_type:
        log.info("WO %s not a generatable content type; skipping.", wo.get("wo_code") or wo.get("wo_id"))
        return None
    topic = wo.get("title", "")
    if _already_covered(business_id, topic):
        log.info("WO '%s' already covered (pgvector); skipping.", topic)
        return None

    grounding = _grounding_context(business_id)
    voice = _brand_voice(business_id)
    reg = _reg_profile(business_id)          # firm-type-aware compliance (RIA vs BD vs non-financial)
    comp_system = _compliance_system(reg)
    # Pass 1 (long-form): a keyword-mapped outline the draft writes from.
    outline = _outline(biz, wo, asset_type, grounding) if asset_type in ("article", "faq") else ""
    # Pass 2: the grounded draft.
    body = _generate_one(biz, wo, asset_type, grounding, outline=outline, voice=voice)
    if not body:
        log.warning("Generation produced no content (LLM unavailable?) for '%s'", topic)
        return None

    # self-eval + bounded auto-revision. KEEP-BEST: _revise is not guaranteed to
    # improve a draft -- a later revision can score LOWER than an earlier one -- so
    # track the highest-scoring usable candidate across the original and every
    # revision and persist THAT, not merely whatever the last round produced.
    revisions = 0
    evaluation = _evaluate(asset_type, wo.get("target_query", ""), body)
    eval_unavailable = not evaluation  # {} => LLM unavailable OR validation failed
    score = float(evaluation.get("score", 0) or 0)
    best_body, best_score, best_eval, best_unavailable = body, score, evaluation, eval_unavailable
    while (not eval_unavailable and score < QUALITY_THRESHOLD
           and revisions < MAX_REVISIONS and evaluation.get("fixes")):
        body = _revise(body, evaluation.get("fixes", [])) or body
        revisions += 1
        evaluation = _evaluate(asset_type, wo.get("target_query", ""), body)
        eval_unavailable = not evaluation
        score = float(evaluation.get("score", 0) or 0)
        if not eval_unavailable and score > best_score:
            best_body, best_score, best_eval, best_unavailable = body, score, evaluation, False
    # Persist the best candidate seen (not the last). best_unavailable carries the
    # original-eval state: if the first eval was usable, the persisted draft has a
    # real eval even when a later round's eval was malformed; if no eval was ever
    # usable, eval_unavailable stays True and the draft still routes to a human.
    body, score, evaluation, eval_unavailable = best_body, best_score, best_eval, best_unavailable

    # Pass 3: SEO/keyword self-check. If important (primary/local) target keywords are missing,
    # do ONE targeted revision to weave them in, and keep it only if coverage actually improved.
    coverage = _keyword_coverage(body, grounding)
    if coverage["important_missing"]:
        fixed = _revise(body, ["Naturally weave in these target SEO keywords that are currently "
                               "missing (no keyword-stuffing, keep it readable): "
                               + ", ".join(coverage["important_missing"][:8])])
        if fixed:
            recov = _keyword_coverage(fixed, grounding)
            if len(recov["covered"]) > len(coverage["covered"]):
                body, coverage = fixed, recov
                revisions += 1

    # compliance gate (firm-type-adapted)
    comp = _compliance(body, system=comp_system)
    comp_pass = comp.get("pass")
    comp_flags = comp.get("flags", [])

    # Compliance AUTO-FIX: rather than dumping a flagged draft on the human as "needs_fix", try
    # once to resolve the issues (strip prohibited claims + add the missing disclosures) and
    # re-screen. If it now passes (or is at least no longer a hard fail), keep the fixed version
    # and record WHAT was changed so the human can confirm the added language is accurate.
    highlighted: list = []
    if comp_pass is False and not eval_unavailable:
        fixed = _compliance_autofix(biz, body, comp_flags, reg=reg)
        if fixed and fixed != body:
            recheck = _compliance(fixed, system=comp_system)
            if recheck.get("pass") is not False:   # passed, or unknown (no LLM) -> human reviews
                body = fixed
                highlighted = [{"type": "compliance", "note": str(f)} for f in comp_flags]
                comp_pass = recheck.get("pass")
                comp_flags = list(recheck.get("flags", []))

    placeholders = _extract_placeholders(body)

    # status:
    #  - a REAL evaluation below threshold, or a REAL compliance failure -> needs_fix
    #  - could-not-evaluate (eval JSON malformed/unavailable) must NOT become a false
    #    needs_fix; it stays pending_review with a flag so a human looks at it.
    status = "pending_review"
    if eval_unavailable:
        comp_flags = list(comp_flags) + [
            "quality evaluation unavailable/malformed -- human must review"]
    elif score < QUALITY_THRESHOLD:
        status = "needs_fix"
    if comp_pass is False:
        status = "needs_fix"

    # quality_notes carries the rubric eval + the SEO keyword-coverage scorecard (CI-3 UI reads it)
    # + the Wave-2 draft-quality scorers (on-page SEO, citation-readiness, fact-check).
    quality_notes = {**(evaluation or {}), "keyword_coverage": coverage}
    try:
        from . import content_quality as _cq
        _kw = list(coverage.get("covered", [])) + list(coverage.get("missing", []))
        _site = grounding if isinstance(grounding, dict) else None
        quality_notes.update(_cq.analyze_draft(
            body, target_query=wo.get("target_query") or "", keywords=_kw,
            site_summary=_site, with_fact_check=True))
    except Exception as e:  # noqa: BLE001 -- quality scoring must never break generation
        log.debug("draft quality analysis skipped: %s", e)

    # Enforce the citation-readiness gate (these scorers used to be advisory only): a draft that
    # scores low on "will an AI quote this?" should go back for a fix, not slip through as ready --
    # this is the on-page lever that most affects whether answer engines cite the content.
    if status == "pending_review":
        cr = quality_notes.get("citation_ready")
        cr_score = cr.get("score") if isinstance(cr, dict) else None
        if isinstance(cr_score, (int, float)) and cr_score < CITATION_READY_MIN:
            status = "needs_fix"
            tips = "; ".join(t.get("fix", "") for t in (cr.get("tips") or [])[:3] if isinstance(t, dict))
            comp_flags = list(comp_flags) + [
                f"citation-readiness {cr_score:.0f}/100 below {CITATION_READY_MIN:.0f}"
                + (f" -- {tips}" if tips else "")]

    _ensure_table()
    with db() as conn:
        row = conn.execute(
            """INSERT INTO content_drafts
               (business_id, work_order_id, asset_type, title, body, target_query,
                quality_score, quality_notes, revision_count, compliance_pass,
                compliance_flags, status, highlighted_sections, placeholders_pending)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (business_id, wo.get("_db_id"), asset_type, topic, body,
             wo.get("target_query"), round(score, 2), json.dumps(quality_notes),
             revisions, comp_pass, json.dumps(comp_flags), status,
             json.dumps(highlighted), json.dumps(placeholders)),
        ).fetchone()
        conn.commit()
    log.info("Draft %d for '%s' (type=%s, score=%.2f, rev=%d, compliance=%s, status=%s, placeholders=%d)",
             row["id"], topic, asset_type, score, revisions, comp_pass, status, len(placeholders))
    return row["id"]


def generate(business_id: int, only_wo: Optional[int] = None) -> list[int]:
    """Generate drafts for the auto content work orders of the latest plan.
    Pulls work orders from the tracking table if present, else from the plan JSON."""
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        wos = []
        # prefer tracked work orders (they carry status + db id)
        try:
            rows = conn.execute(
                "SELECT id, wo_code, title, capability, execution, instruction "
                "FROM work_orders WHERE business_id=%s", (business_id,)
            ).fetchall()
            for r in rows:
                wos.append({"_db_id": r["id"], "wo_code": r["wo_code"], "title": r["title"],
                            "capability": r["capability"], "execution": r["execution"],
                            "instruction": r["instruction"]})
        except Exception:
            pass
        if not wos:
            plan = conn.execute(
                "SELECT plan FROM strategy_plans WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,),
            ).fetchone()
            if plan:
                p = plan["plan"] if isinstance(plan["plan"], dict) else json.loads(plan["plan"])
                wos = p.get("work_orders", [])
    biz = dict(biz)
    created = []
    for wo in wos:
        if only_wo and wo.get("_db_id") != only_wo:
            continue
        # only attempt auto-executable content work orders
        if (wo.get("execution") or "auto") not in ("auto", "semi"):
            continue
        did = generate_for_wo(business_id, wo, biz)
        if did:
            created.append(did)
    log.info("Generated %d draft(s) for business %d", len(created), business_id)
    return created


# ----------------------------------------------------------------------------
# Review workflow
# ----------------------------------------------------------------------------
def list_drafts(business_id: int) -> None:
    _ensure_table()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, asset_type, title, quality_score, compliance_pass, status, revision_count "
            "FROM content_drafts WHERE business_id=%s ORDER BY id DESC", (business_id,)
        ).fetchall()
    for r in rows:
        print(f"  [{r['id']}] {r['status']:<14} q={r['quality_score']} "
              f"compliance={r['compliance_pass']} rev={r['revision_count']} "
              f"{r['asset_type']}: {r['title']}")
    if not rows:
        print("  (no drafts yet)")


def approve(draft_id: int, reviewer: str, override_reason: Optional[str] = None) -> None:
    """Approve a draft and promote it into the assets table (the only path to
    'published' state). Human action only.

    Records an immutable compliance sign-off (approver, verdict, flags, body hash) for the
    regulatory recordkeeping requirement. A draft that was never compliance-screened
    (compliance_pass IS NULL) can only be approved with an explicit `override_reason` (a
    principal attestation); a hard compliance FAILURE still cannot be published at all.

    Idempotent: a double-submit (impatient reviewer, retried request, two editors at
    once) must not mint duplicate assets. The draft row is locked FOR UPDATE so the
    second caller serializes behind the first, then sees status='approved' and returns
    the existing asset instead of inserting again."""
    with db() as conn:
        d = conn.execute("SELECT * FROM content_drafts WHERE id=%s FOR UPDATE",
                         (draft_id,)).fetchone()
        if not d:
            raise SystemExit(f"No draft {draft_id}")
        if d["status"] == "approved":
            conn.commit()   # release the row lock held by FOR UPDATE
            log.info("Draft %d already approved (asset %s); no-op.",
                     draft_id, d.get("published_asset_id"))
            return
        # Compliance gate, enforced server-side (not just hidden in the UI): a draft that FAILED
        # the deterministic compliance screen must never be promoted to a published asset. For
        # the regulated (e.g. financial-services) context this module exists to protect,
        # approving past a failed screen is exactly the failure mode the gate prevents. Resolve
        # the flags by editing the draft (which re-screens it), then approve.
        if d.get("compliance_pass") is False:
            conn.commit()   # release the FOR UPDATE lock before raising
            flags = d.get("compliance_flags") or []
            raise ValueError(
                "This draft failed the compliance screen and can't be published"
                + (f" (flags: {', '.join(str(f) for f in flags)})" if flags else "")
                + ". Edit it to resolve the issues, which re-screens it, then approve."
            )
        # Unresolved [INSERT: ...] placeholders are facts the human still has to supply -- a
        # draft can't go live with "[INSERT: contact email]" in it. Block until they're filled.
        pending_ph = d.get("placeholders_pending") or []
        if pending_ph:
            conn.commit()   # release the FOR UPDATE lock before raising
            raise ValueError(
                f"This draft still has {len(pending_ph)} placeholder(s) to fill in before it can "
                f"publish: {', '.join(str(p) for p in pending_ph)}. Edit the draft to replace them, "
                "then approve."
            )
        # An UNSCREENED draft (compliance_pass IS NULL) requires an explicit principal attestation.
        if d.get("compliance_pass") is None and not (override_reason or "").strip():
            conn.commit()
            raise ValueError(
                "This draft wasn't compliance-screened (the screener was unavailable). A principal "
                "must provide a sign-off reason to approve it."
            )
        # Seed a short summary (for the Published list) + published_status='pending' so the owner
        # can paste the live URL later. No site/social integration yet -> the link is manual.
        body = (d.get("body") or "").strip()
        summary = (body[:280] + "…") if len(body) > 280 else body
        # Copy the draft's compliance verdict onto the asset: the publish runner re-checks
        # assets.compliance_pass IS TRUE before any auto-post (Integrations Phase 2).
        asset = conn.execute(
            """INSERT INTO assets (business_id, work_order_id, asset_type, title, surface, meta,
                                   summary, published_status, compliance_pass)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id""",
            (d["business_id"], d["work_order_id"], d["asset_type"], d["title"],
             "own_site", json.dumps({"from_draft": draft_id}), summary, d.get("compliance_pass")),
        ).fetchone()
        conn.execute(
            "UPDATE content_drafts SET status='approved', reviewer=%s, reviewed_at=now(), "
            "published_asset_id=%s, updated_at=now() WHERE id=%s",
            (reviewer, asset["id"], draft_id),
        )
        # advance the linked work order if present
        if d["work_order_id"]:
            conn.execute(
                "UPDATE work_orders SET status='done', completed_at=COALESCE(completed_at, now()), "
                "updated_at=now() WHERE id=%s AND status IN ('pending','in_progress')",
                (d["work_order_id"],),
            )
        # Immutable compliance sign-off record (FINRA 2210 / SEC recordkeeping).
        body_hash = hashlib.sha256((d.get("body") or "").encode("utf-8")).hexdigest()
        conn.execute(
            "INSERT INTO compliance_signoffs (business_id, draft_id, asset_id, approver, "
            "compliance_pass, compliance_flags, placeholders, body_hash, override_reason) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (d["business_id"], draft_id, asset["id"], reviewer, d.get("compliance_pass"),
             json.dumps(d.get("compliance_flags") or []), json.dumps(d.get("placeholders_pending") or []),
             body_hash, (override_reason or "").strip() or None),
        )
        conn.commit()
    log.info("Draft %d approved by %s -> asset %d", draft_id, reviewer, asset["id"])


def reject(draft_id: int, reviewer: str, notes: Optional[str]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE content_drafts SET status='rejected', reviewer=%s, reviewed_at=now(), "
            "quality_notes = quality_notes || %s::jsonb, updated_at=now() WHERE id=%s",
            (reviewer, json.dumps({"reject_notes": notes or ""}), draft_id),
        )
        conn.commit()
    log.info("Draft %d rejected by %s", draft_id, reviewer)


def update_draft(draft_id: int, *, title: Optional[str] = None, body: Optional[str] = None,
                 business_id: Optional[int] = None) -> bool:
    """Edit a draft's title/body BEFORE approval -- the human can fix a fact or adjust tone,
    then approve the edited version. Only editable while it is NOT yet an asset (status not
    'approved' and no published_asset_id); an approved/published draft is immutable. Scopes to
    business_id when given. Returns True if a row was updated.

    A human edit MUST NOT inherit the AI version's quality/compliance verdict (else the UI
    would show 'checks passed' for un-re-screened content). So on every edit we RE-SCREEN the
    effective body with the deterministic (no-LLM, non-injectable) compliance check and reset
    the stale signals: compliance_pass=False if a hard rule trips, else NULL (unscreened --
    the UI shows 'not checked yet', not a false pass); quality_score is cleared."""
    if title is None and body is None:
        return False
    with db() as conn:
        # Lock the row so the edit + re-screen are atomic relative to approve(), and so a
        # title-only edit still re-screens the (unchanged) body.
        d = conn.execute(
            "SELECT body, status, published_asset_id, business_id FROM content_drafts "
            "WHERE id=%s FOR UPDATE", (draft_id,),
        ).fetchone()
        if (not d or d["status"] == "approved" or d["published_asset_id"] is not None
                or (business_id is not None and d["business_id"] != business_id)):
            conn.commit()   # release the FOR UPDATE lock
            return False
        new_body = body if body is not None else d["body"]
        flags = _deterministic_compliance(new_body or "")
        comp_pass = False if flags else None
        comp_flags = flags or ["content edited after screening -- re-screen recommended"]
        # Re-extract the [INSERT: ...] checklist from the edited body (the human may have filled
        # some in) and clear highlighted_sections -- editing IS the human review of those.
        placeholders = _extract_placeholders(new_body or "")
        sets, args = [], []
        if title is not None:
            sets.append("title=%s"); args.append(title)
        if body is not None:
            sets.append("body=%s"); args.append(body)
        sets += ["quality_score=NULL", "compliance_pass=%s", "compliance_flags=%s",
                 "placeholders_pending=%s", "highlighted_sections='[]'::jsonb", "updated_at=now()"]
        args += [comp_pass, json.dumps(comp_flags), json.dumps(placeholders)]
        conn.execute(f"UPDATE content_drafts SET {', '.join(sets)} WHERE id=%s",
                     tuple(args) + (draft_id,))
        conn.commit()
    log.info("Draft %d edited (re-screened: compliance_pass=%s)", draft_id, comp_pass)
    return True


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="AI content generator (drafts only; human approves)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--business-id", type=int, required=True)
    g.add_argument("--wo", type=int)
    l = sub.add_parser("list"); l.add_argument("--business-id", type=int, required=True)
    a = sub.add_parser("approve"); a.add_argument("--draft", type=int, required=True); a.add_argument("--reviewer", required=True)
    r = sub.add_parser("reject"); r.add_argument("--draft", type=int, required=True); r.add_argument("--reviewer", required=True); r.add_argument("--notes")
    args = ap.parse_args()
    if args.cmd == "generate":
        generate(args.business_id, args.wo)
    elif args.cmd == "list":
        list_drafts(args.business_id)
    elif args.cmd == "approve":
        approve(args.draft, args.reviewer)
    elif args.cmd == "reject":
        reject(args.draft, args.reviewer, args.notes)


if __name__ == "__main__":
    main()
