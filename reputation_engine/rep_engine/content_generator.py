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
from datetime import datetime, timezone
from typing import Optional


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
from pydantic import ValidationError

try:
    from . import ai_state_audit as llm   # reuse the orchestrator LLM plumbing
    from . import textutils as _tu
    from . import grounding_coverage as _gc
    from .llm_schemas import ComplianceResult, EvalResult
except ImportError:  # pragma: no cover
    import ai_state_audit as llm  # type: ignore
    import textutils as _tu  # type: ignore
    import grounding_coverage as _gc  # type: ignore
    from llm_schemas import ComplianceResult, EvalResult  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("content_generator")


QUALITY_THRESHOLD = float(os.getenv("CONTENT_QUALITY_THRESHOLD", "0.75"))   # PH 2
# Minimum citation-readiness (0-100, "will an AI quote this?") for a draft to pass as ready rather
# than going back for a fix. Was advisory-only; now an enforced gate (Phase D).
CITATION_READY_MIN = float(os.getenv("CONTENT_CITATION_READY_MIN", "55"))
MAX_REVISIONS = int(os.getenv("CONTENT_MAX_REVISIONS", "4"))                # PH 3 — revise harder
# Extra targeted revision passes for the citation-readiness gate (the on-page lever that decides
# whether AI will quote the piece) before a draft is HELD back for an author instead of shown.
MAX_CITATION_REVISIONS = int(os.getenv("CONTENT_MAX_CITATION_REVISIONS", "2"))

# Capabilities that this module knows how to generate (others stay manual).
# NOTE: schema_markup is NOT here — schema (JSON-LD) is a website/developer task, not editorial
# content, so it lives on the task board as a "website fix", never in the content section.
GENERATABLE = {
    "content_writing": "article",
    # A local page-1 goal's anchor piece: a geo landing page. (Was un-generatable, so the
    # "Generate draft" button on local work orders silently produced nothing and failed the job.)
    "local_content_creation": "local_page",
    "review_generation": "review_request",
    # Rich-media capabilities — ROUTED to rich_media_generator (see _RICH_MEDIA_CAP_MAP + the
    # prologue in generate_for_wo). Listed here so capability matching / UI doesn't treat these
    # work orders as non-generatable.
    "deep_content":     "deep_article",
    "podcast_creation": "podcast",
    "slide_deck":       "slide_deck",
    "infographic":      "infographic",
    "explainer_video":  "explainer_video",
    "research_brief":   "research_brief",
}

# Work-order capability -> rich_media_generator asset_type list. Any capability present here is
# intercepted at the top of generate_for_wo() and routed to rich_media_generator (multi-source
# NotebookLM synthesis, or its in-house LLM fallback) instead of the single-source LLM path.
_RICH_MEDIA_CAP_MAP: dict[str, list[str]] = {
    "podcast_creation": ["podcast"],
    "slide_deck":       ["slide_deck"],
    "infographic":      ["infographic"],
    "explainer_video":  ["explainer_video"],
    "research_brief":   ["research_brief"],
    "deep_content":     ["deep_article", "blog_series", "newsletter"],
}
# asset_type inferred from work-order title keywords as a fallback (schema deliberately excluded).
# NOTE: intentionally NO generic "blog"/"newsletter"/"brief" hints here — those collide with normal
# content/visual/production work orders (e.g. Track-3 "Blog: <kw>" pieces must stay 'article', and
# "…brief" WOs must not become research_briefs). Rich-media WOs route by CAPABILITY, not title.
TITLE_HINTS = [
    ("faq", "faq"), ("bio", "bio"),
    ("article", "article"), ("post", "gbp_post"), ("review", "review_request"),
    ("podcast", "podcast"), ("slide", "slide_deck"),
    ("infographic", "infographic"), ("explainer", "explainer_video"),
]

# When the user EXPLICITLY picks a content_type in "Create Content", map it straight to the
# generation asset_type — bypassing the title-keyword guesser (TITLE_HINTS), which mis-routed
# 'Blog post: ...' to gbp_post and collapsed white_paper/landing_page unpredictably. Only text
# content_types need this; rich-media types are selected directly in generate_for_wo's rich branch.
_CT_ASSET_OVERRIDE = {
    # blog + white_paper map to their OWN asset_type (not "article") so each gets a DISTINCT
    # generation spec -- otherwise a gap's multi-type batch (article+blog+white_paper) produced three
    # near-identical "about" pages (duplicate content). See the per-type specs in _gen_prompt().
    "article": "article", "blog": "blog", "white_paper": "white_paper", "landing_page": "article",
    "faq": "faq", "local_page": "local_page",
}




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
                published_asset_id BIGINT, content_hash TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now())
        """)
        conn.execute("ALTER TABLE content_drafts ADD COLUMN IF NOT EXISTS content_hash TEXT")
        conn.commit()


# ----------------------------------------------------------------------------
# Content dedup -- avoid regenerating content we've already published.
# ----------------------------------------------------------------------------
def _already_covered(business_id: int, topic: str) -> bool:
    """Cheap pre-generation dedup: skip if we've ALREADY PUBLISHED an asset with this exact
    title for the business. Exact-title only (case-insensitive) -- a conservative gate that
    catches obvious re-runs without blocking legitimate new angles. Near-duplicate semantic
    dedup (pgvector) is a deferred enhancement; the post-generation content_hash check (below)
    catches byte-identical bodies. Never raises -- returns False on any error so a lookup
    problem can't block generation."""
    t = (topic or "").strip()
    if not t:
        return False
    try:
        with db() as conn:
            row = conn.execute(
                "SELECT 1 FROM assets WHERE business_id=%s AND lower(btrim(title))=lower(%s) LIMIT 1",
                (business_id, t),
            ).fetchone()
        return bool(row)
    except Exception as e:  # noqa: BLE001 -- dedup must never break generation
        log.debug("_already_covered lookup skipped: %s", e)
        return False


def _duplicate_body(business_id: int, content_hash: str) -> bool:
    """Post-generation exact-content dedup: True if this exact body (by sha256) already exists
    as a published asset OR an approved draft for the business. Used to FLAG (not drop) a
    byte-identical duplicate for human review. Never raises."""
    if not content_hash:
        return False
    try:
        with db() as conn:
            row = conn.execute(
                """SELECT 1 FROM assets WHERE business_id=%s AND body_hash=%s
                   UNION ALL
                   SELECT 1 FROM content_drafts
                   WHERE business_id=%s AND content_hash=%s AND status IN ('approved','pending_review','needs_fix','held')
                   LIMIT 1""",
                (business_id, content_hash, business_id, content_hash),
            ).fetchone()
        return bool(row)
    except Exception as e:  # noqa: BLE001
        log.debug("_duplicate_body lookup skipped: %s", e)
        return False


# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------
_GEN_SYSTEM_BASE = (
    "You are an expert content writer AND answer-engine-optimization (AEO/GEO) + SEO strategist for "
    "a reputation program that publishes ACCURATE, helpful, well-structured content so it becomes "
    "what AI assistants (ChatGPT, Perplexity, Gemini, Google AI Overview) and Google surface about a "
    "business. GROUND every claim in the REAL facts provided (the business's crawled website + "
    "profile) and use them CONFIDENTLY -- the business's OWN website is authoritative for its name, "
    "address, phone, email, services, and hours, so state those plainly and NEVER add "
    "'unverified'/'to be confirmed' caveats to the business's own facts. The output MUST be "
    "PUBLISH-READY AS-IS: do NOT leave [INSERT: ...] placeholders, 'coming soon', or 'to be confirmed' "
    "stubs in the body. If a specific detail is NOT available from the website/profile, WRITE AROUND "
    "it -- omit it gracefully, use accurate general wording, or point the reader to the website / "
    "contact form -- rather than inserting a placeholder or inventing the detail. NEVER output the "
    "literal characters '[INSERT'. Handle the common cases WITHOUT a placeholder: do NOT state a "
    "specific star rating or review count -- instead point readers to 'our reviews on Google' and never "
    "guess a number; for any affiliate/partner you cannot name specifically, refer to it generally. If "
    "completing a sentence would require a "
    "specific you don't have, state it generally or LEAVE THE SENTENCE OUT entirely. "
    "WRITE AS A FINISHED, PUBLISHED PAGE in a confident voice -- state the business's facts plainly as "
    "fact. Do NOT hedge every fact with 'at time of drafting', 'may change', 'should be independently "
    "verified', or similar. Do NOT write any editor- or reviewer-facing notes in the body (NEVER "
    "'before publication...', 'in this draft', 'verify before publishing', 'do not publish this "
    "section', 'add verified URLs here', 'set a calendar reminder to re-verify'). Any required "
    "legal/compliance disclaimer goes in ONE short block at the very END of the page, NEVER at the top. "
    "YOUR PRIMARY GOAL is to make this content maximally CITABLE by AI answer engines (ChatGPT, "
    "Perplexity, Gemini, Google AI Overviews) -- getting the AI to surface accurate facts about this "
    "business is what this content is FOR; SEO/keyword ranking is only a secondary benefit. STRUCTURE "
    "EVERY PIECE FOR AI CITATION: "
    "(1) The page MUST OPEN, immediately after the H1, with a crisp 40-60 word DIRECT ANSWER to the "
    "core question (front-load the key fact -- most AI citations come from the top of the page), and "
    "OPEN EACH H2 SECTION the same way -- a self-contained 1-2 sentence answer an AI can lift out of "
    "context. Do NOT put any disclaimer, disclosure, or caveat before that answer; (2) phrase H2/H3 "
    "headings AS the real questions a reader would ask (they map to AI prompts); (3) include a short "
    "FAQ / Q&A section near the end; (4) give a concrete, ATTRIBUTABLE statistic roughly every 150-200 "
    "words -- use ONLY real numbers you can source (industry data, official/regulatory figures, the "
    "parent company's public data) and NEVER invent one; (5) CITE authoritative primary sources INLINE "
    "as markdown links (.gov/.edu/official -- e.g. the relevant regulator or licensing body, official "
    "statistics agencies (.gov), or a recognized industry association): inline citations to "
    "authoritative sources are a top AI-citation lever; "
    "(5b) present AT LEAST TWO of the provided real statistics AS SHORT DIRECT QUOTATIONS with inline "
    "attribution -- put the quantitative claim in quotation marks and attribute it to its source, e.g. "
    "\"<a real figure from your provided sources>,\" according to [the named source](url) "
    "-- because ADDING ATTRIBUTED QUOTATIONS is the single strongest MEASURED lever for getting content "
    "quoted by AI answer engines (Princeton GEO study, +41% vs +33% for a bare stat); quote ONLY the "
    "real, provided sources/numbers, and NEVER invent a quote or attribute words to a specific named "
    "person; (6) name the business + city + service clearly for entity clarity, but NATURALLY — enough "
    "for an AI to attribute the facts, WITHOUT repeating the name or city in every sentence (over-"
    "repetition reads as keyword-stuffing, which hurts believability AND AI citation); use 'we'/'our' "
    "where the name isn't needed; "
    "(7) keep sections ~200-400 words with bullets/tables so a passage lifts cleanly; (8) where an "
    "image strengthens the page, insert a markdown image with DESCRIPTIVE alt text as ![alt describing "
    "the image](IMAGE: short generation prompt); (9) add a visible 'Last updated: <MONTH YEAR>' line "
    "using the CURRENT month and year given in the context below (a real date, never a placeholder). "
    "Weave in the target search keywords ONLY where they fit naturally (secondary to the above; never "
    "keyword-stuff). Only cover "
    "topics and FAQ questions that are SPECIFIC to this business and directly serve THIS page's "
    "stated purpose and the business's actual services -- do NOT pad the page with generic industry "
    "questions that don't fit it (e.g. broad 'how to enter this industry' or generic eligibility "
    "questions unrelated to THIS page); drop any provided keyword that doesn't genuinely belong here. "
    "Directly address the gap / narrative the content is meant to fix. Never fabricate facts, "
    "credentials, reviews, or statistics. "
    # --- Anti-generic ("AI slop") spec: what separates distinctive, authoritative content from
    # generic machine output (research: NN/g scannability; Google helpful-content 'beyond the obvious').
    "WRITE DISTINCTIVE, SPECIFIC CONTENT -- NOT GENERIC AI FILLER. (a) SPECIFICITY MANDATE: every "
    "section MUST contain at least one CONCRETE anchor -- a named entity, an exact number, a real place, "
    "or a dated/specific example -- never a vague generality. (b) BAN generic 'AI-slop' phrasing: do NOT "
    "use formulaic openers/closers ('In today's fast-paced world', 'In conclusion', 'In summary', "
    "'Ultimately', 'At the end of the day', 'When it comes to'), non-committal hedges ('it's important "
    "to note', 'it's worth noting', 'generally speaking', 'that being said'), filler transitions "
    "('furthermore', 'moreover'), or buzzword vocabulary ('delve', 'leverage', 'foster', 'seamless', "
    "'tapestry', 'landscape', 'realm', 'transformative', 'game-changer', 'plethora', 'unlock', 'elevate', "
    "'empower', 'cutting-edge', 'unparalleled', 'dive into', 'in this article we'll explore'). State "
    "things plainly and specifically instead. (c) ADD NET-NEW VALUE: use the business's REAL specifics "
    "and local facts and a clear, defensible point of view; do NOT just restate generic consensus an AI "
    "already knows -- give a reader something specific to this business and place. (d) READABILITY: write "
    "at a grade 6-8 level (grade 10-12 only for a white paper) -- short sentences (~15-20 words average), "
    "active voice, one idea per paragraph (<=150 words), scannable with descriptive headings, bullets, "
    "and tables. "
    # --- Google helpful-content + E-E-A-T + gen-AI-content policy (rater guidelines + Search Essentials)
    "GOOGLE HELPFUL-CONTENT + E-E-A-T (people-first, per Google's creating-helpful-content + "
    "search-quality-rater guidelines): write for a PERSON who needs this, not for a search engine. "
    "Demonstrate E-E-A-T — (Experience) specific, first-hand detail only someone who actually does this "
    "would know; (Expertise) correct, sufficient depth; (Authoritativeness) name the business + its "
    "credentials and cite authoritative sources; (Trust) transparent and honest, with no exaggerated or "
    "unsupported claims. Satisfy the reader's intent so completely they need not search again — leave no "
    "obvious question unanswered. This must be ORIGINAL, genuinely useful content grounded in THIS "
    "business's real facts — never thin, templated, mass-produced, or written mainly to rank (Google's "
    "scaled-content-abuse and gen-AI-content policies reward helpful original content and act against the "
    "opposite; AI assistance is fine, low-value output is not). For internal links, use DESCRIPTIVE anchor "
    "text naming the linked page's topic (never 'click here'/'read more'), and place each image directly "
    "beside the text it illustrates. "
    "Output ONLY the asset content -- no preamble."
)


# Finance-specific writing EXEMPLARS, appended ONLY for a regulated-finance tenant. The base prompt's
# rules (write around a missing specific; cite authoritative sources; >=2 attributed quotations) stay
# universal; these just give the finance tenant its concrete examples back (broker-dealer affiliate,
# income disclosure, SEC/EDGAR, a LIMRA quotation).
_GEN_FINANCE_MODULE = (
    " For this regulated-finance business specifically: for a securities/broker-dealer disclosure, name "
    "the affiliate by its known public name from the context or say 'the affiliated broker-dealer' "
    "generally, and reference any income-disclosure statement only in general terms; good authoritative "
    "sources to cite inline include the state regulator, SEC/EDGAR, and the parent company's investor "
    "page; a strong attributed-quotation example is \"About 51% of U.S. adults own life insurance,\" "
    "according to [LIMRA's 2024 Barometer Study](url)."
)


def _gen_system(license_policy: str = "", regulated_financial: bool = False) -> str:
    """The generation system prompt for ONE tenant. `license_policy` is the profile-driven license /
    sensitive-ID ban -- empty ('') for a tenant that doesn't suppress specific credential numbers (the
    GENERIC default: NO license-number ban at all). `regulated_financial` appends the finance writing
    exemplars. NO_NEGATIVE_DISAMBIGUATION stays agnostic and is always present. The module `GEN_SYSTEM`
    alias below = this with NO license + no finance module (the finance-free default); per-tenant
    prompts are built at the generation call site from the business's profile."""
    prompt = _GEN_SYSTEM_BASE
    if regulated_financial:
        prompt += _GEN_FINANCE_MODULE
    return prompt + license_policy + llm.NO_NEGATIVE_DISAMBIGUATION_POLICY


GEN_SYSTEM = _gen_system()   # finance-free GENERIC alias; per-tenant prompt built at the call site


# Common words that must NOT count as topical relevance in keyword scoping. Without this, a shared
# STOPWORD gives a false overlap -- e.g. "About / Entity Disambiguation page WITH regulatory
# credentials" matched "life insurance WITH lupus" on the single token "with", pulling generic
# off-topic questions (medical-underwriting, unrelated career FAQs) onto an entity page.
_KW_STOPWORDS = frozenset(
    "the a an and or but for with without your you our their they them this that these those from into "
    "out over can could will would should may might get got how what why who when where which does did "
    "are is was were be been being have has had not no yes all any one two some more most best top near "
    "about of to in on at by as it its we us my me do if so than then he she his her".split())


def _kw_tokens(text: str) -> set:
    """Content tokens for relevance scoring: >=3 chars, minus stopwords."""
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if t not in _KW_STOPWORDS}


def _scope_keywords(allkw: list, target_query: str | None, limit: int = 12) -> list:
    """Rank the business's keyword set by relevance to THIS piece (CONTENT-token overlap with its
    target query/topic, stopwords excluded) so two different pieces get different, on-topic keywords
    instead of the same business-wide top-15 on every draft. reputation_defense terms are always kept
    (they matter on every piece). No target query -> fall back to top-priority."""
    if not target_query:
        return allkw[:15]
    qtoks = _kw_tokens(target_query)
    scored = []
    for k in allkw:
        kt = _kw_tokens(str(k.get("keyword") or ""))
        scored.append((len(qtoks & kt), 1 if k.get("kind") == "reputation_defense" else 0,
                       k.get("priority") or 0, k))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    relevant = [t for t in scored if t[0] > 0 or t[1] == 1]
    return [t[3] for t in (relevant if relevant else scored)[:limit]]


def _grounding_context(business_id: int, target_query: str | None = None, biz: dict | None = None) -> dict:
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
                "ORDER BY priority DESC NULLS LAST, keyword LIMIT 60", (business_id,)).fetchall()
            allkw = [{"keyword": r["keyword"], "kind": r.get("kind"),
                      "intent": r.get("intent"), "priority": r.get("priority")} for r in rows]
            # Scope to THIS piece's target query so each draft targets its own keywords, not the
            # same business-wide top-15 on every piece.
            keywords = _scope_keywords(allkw, target_query)
    except Exception:  # noqa: BLE001 -- best-effort: missing table or empty result degrades to no keywords
        keywords = []
    # Authoritative citation sources + real datable statistics (the #1 GEO/citability lever). The
    # authoritative_sources registry is the FINANCE source pack (LIMRA/ACLI/SEC/FINRA/IRS), so inject
    # it ONLY for a tenant whose profile selects that pack (authoritative_source_pack == 'financial').
    # A generic tenant gets '' here -- the prompt still tells it to cite .gov/official sources inline,
    # sourced dynamically -- so no finance sources leak into a dentist's or SaaS's draft.
    authoritative = ""
    try:
        from . import business_profile as _bp
        # Use the already-loaded biz row (pure derive, no query) when the caller passes it; only fall
        # back to a for_business load when it doesn't -- avoids a duplicate profile query per piece.
        _pack = (_bp.derive(biz) if biz is not None else _bp.for_business(business_id)
                 ).get("authoritative_source_pack") or ""
        if _pack == "financial":
            from . import authoritative_sources as _authsrc
            authoritative = _authsrc.grounding_for_business(business_id)
    except Exception:  # noqa: BLE001 -- best-effort
        authoritative = ""
    return {"site_facts": site_facts, "gap_focus": gap_focus, "keywords": keywords,
            "authoritative": authoritative}


_BRIEF_WORDS = {"white_paper": 1500, "blog": 800, "article": 700, "faq": 600, "local_page": 650,
                "landing_page": 500, "gbp_post": 120, "social_post": 100, "bio": 350, "video_script": 400,
                "deep_article": 2200, "newsletter": 550, "blog_series": 900}
_BRIEF_READ = {"white_paper": "Grade 10-12 (authoritative)", "gbp_post": "Grade 6-8 (very plain)",
               "social_post": "Grade 6-8 (very plain)", "video_script": "Grade 6-8 (spoken)"}
_BRIEF_STRUCT = {
    "faq": "6-10 Q&A pairs; each heading phrased as the exact question a buyer asks.",
    "article": "Answer-first 40-60 word intro; H2/H3 headings phrased as questions; one quotable stat per section; short FAQ near the end.",
    "blog": "Answer-first intro; scannable H2 sections; a takeaway per section; internal links; short FAQ.",
    "local_page": "Geo landing page: city + service in the H1; local proof (reviews/NAP); embedded map; a local FAQ.",
    "white_paper": "Executive summary; data-backed sections with citations; conclusion + CTA.",
    "landing_page": "Clear value-prop H1; benefits; proof; one strong CTA.",
    "video_script": "Hook (0-3s); 3-5 talking points; on-screen text cues; CTA + shot list.",
    "social_post": "One idea; hook first line; a link back to the owned page.",
}


def piece_brief(business_id: int, wo: dict) -> dict:
    """A DETERMINISTIC, no-LLM content SPEC for a to-produce piece, surfaced BEFORE drafting so the
    owner sees what it must contain: scoped keywords, a length + readability target, the structure,
    and the exact AI gap it closes. (The full grounding + outline are still computed at draft time.)"""
    at = _asset_type_for(wo) or "article"
    ct = wo.get("content_type") or at
    tq = _gc.scope_query(wo)   # same topic-key the draft grounds on -> plan advisory can't drift from draft
    keywords: list = []
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT keyword, kind, priority FROM target_keywords WHERE business_id=%s "
                "ORDER BY priority DESC NULLS LAST, keyword LIMIT 60", (business_id,)).fetchall()
        allkw = [{"keyword": r["keyword"], "kind": r.get("kind"), "priority": r.get("priority")} for r in rows]
        keywords = [k["keyword"] for k in _scope_keywords(allkw, tq, limit=8) if k.get("keyword")]
    except Exception:  # noqa: BLE001 -- best-effort: no keyword table -> empty
        keywords = []
    # Grounding-coverage advisory for the plan/To-Produce surface: will this piece have source facts?
    # Wrapped independently -- GET /work-orders/{id}/brief has no outer guard, and coverage() (though
    # total) must never 500 this read endpoint. Same scope_query key as the draft, so no drift.
    try:
        coverage = _gc.coverage(business_id, tq)
    except Exception:  # noqa: BLE001
        coverage = None
    return {
        "asset_type": at, "content_type": ct,
        "primary_keyword": keywords[0] if keywords else None,
        "keywords": keywords,
        "word_count_target": _BRIEF_WORDS.get(ct, _BRIEF_WORDS.get(at, 700)),
        "readability_target": _BRIEF_READ.get(ct, _BRIEF_READ.get(at, "Grade 8-10 (plain, scannable)")),
        "structure": _BRIEF_STRUCT.get(ct, _BRIEF_STRUCT.get(at, "Answer-first; clear H2/H3 headings; a short FAQ.")),
        "closes_gap": (wo.get("gap_specifics") or {}).get("source_query"),
        "gap_source": wo.get("gap_source"),
        "coverage": coverage,
    }


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
            # reputation_defense terms (is-it-a-scam / legitimate / complaints / reviews) are the
            # highest-leverage phrases on a defense/disambiguation page -- force them in too, not just
            # primary/local SEO terms.
            if k.get("kind") in ("primary", "local", "reputation_defense"):
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
        "article": "Write the DEFINITIVE, canonical 600-900 word page on this topic in markdown "
                   "(this is the authoritative reference page) with a clear H1 and question-style "
                   "subheadings, answering the target question accurately and working in the target "
                   "keywords naturally.",
        "blog": "Write an ~800 word blog post in markdown that takes ONE specific, focused angle on "
                "the topic — a single question, a short how-to, or a timely take. Do NOT write a broad "
                "'about/overview/who-we-are' page (that is the canonical article's job). Open "
                "answer-first, use scannable H2 sections each ending in a takeaway, and add a short "
                "FAQ. Where the definitive company page already covers the basics, briefly reference "
                "it rather than restating it, so this reads as a complementary piece, not a duplicate.",
        "white_paper": "Write an in-depth white paper (1,200-1,800 words) in markdown for a "
                       "sophisticated reader: an executive summary, several evidence- and data-backed "
                       "sections that each cite a source, and a conclusion with a CTA. Go materially "
                       "DEEPER and more formal than a web article — this is a distinct, cited format, "
                       "NOT a longer restatement of the 'about' page. Use [INSERT: ...] placeholders "
                       "for facts you don't have; never fabricate data or citations.",
        "bio": "Write a professional bio page in markdown (250-400 words) establishing "
               "authority and trust, grounded in the real facts above.",
        "gbp_post": "Write a short Google Business Profile post (80-150 words), friendly and "
                    "local, naturally including a local keyword.",
        "review_request": "Write a short, warm review-request message (SMS + email versions) "
                          "asking a happy client to leave a Google review, with a placeholder for the link.",
        # Rich-media long-form types generated via the in-house LLM path. (The NotebookLM
        # multi-source path in rich_media_generator.py produces richer output when a key is set;
        # these specs are the deterministic LLM fallback / when routed here directly.)
        "deep_article": "Write a long-form thought-leadership article (1,500-2,500 words) in "
                        "markdown with a clear H1, H2 subheadings, and a concrete conclusion. Use "
                        "[INSERT: ...] placeholders for unknown facts. No performance promises, "
                        "guaranteed-return language, or unverifiable superlatives.",
        "blog_series": "Generate outlines for THREE related blog posts. Each outline: title, "
                       "target query, 5-7 heading structure, key points, recommended word count, "
                       "and CTA. Format in markdown. No fabricated facts.",
        "newsletter": "Write a newsletter brief (400-600 words) covering reputation progress "
                      "highlights. Include 3 subject-line options, preview text, 3-4 content "
                      "sections, a key takeaway, and a CTA. Tone: warm, credible.",
    }
    spec = specs.get(asset_type, "Write the requested asset in markdown.")
    kw = grounding.get("keywords") or []
    kw_line = ""
    if kw:
        kw_line = ("Target search keywords to weave in NATURALLY (do not keyword-stuff): "
                   + ", ".join(str(k.get("keyword")) for k in kw if k.get("keyword")) + "\n")
    parts = [
        # Real current date so the writer can stamp a 'Last updated' freshness line with an actual
        # month/year (a real freshness marker, ~2x more citable) instead of an [INSERT] placeholder.
        f"Current date (use for any 'Last updated' line): {datetime.now(timezone.utc):%B %Y}",
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
        # Owner-provided brand rules (ABSOLUTE) + uploaded source material (authoritative facts). This
        # is the client's own material — obey the rules and ground the content in these facts.
        ("CLIENT BRAND RULES + UPLOADED SOURCE MATERIAL (authoritative — the rules are ABSOLUTE and "
         "override everything; ground your facts in this material and do not contradict it):\n"
         + grounding["client_material"] + "\n") if grounding.get("client_material") else "",
        "WHAT AI CURRENTLY GETS WRONG / THE GAP THIS CONTENT MUST CLOSE:",
        # The SPECIFIC weak AI answer this piece exists to fix leads; the full gap model is background.
        (f"THIS PIECE MUST CLOSE (the specific weak AI answer): \"{wo.get('target_query')}\"")
        if wo.get("target_query") else "",
        grounding.get("gap_focus") or "(general trust & visibility)",
        "",
        # Authoritative sources to cite inline + real statistics to quote -- the biggest AI-citation lever.
        grounding.get("authoritative") or "",
        "" if grounding.get("authoritative") else "",
        f"Work order: {title}",
        f"Instruction: {instr}" if instr else "",
        kw_line + f"Target question this should answer when someone asks AI: "
        f"{wo.get('target_query','(general trust/visibility)')}",
        # SERP coverage terms + questions + target length from the pages ACTUALLY ranking for this
        # query (serp_benchmark), so the draft covers what the top-ranking pages cover.
        ("SERP COVERAGE TERMS (cover these naturally, like the top-ranking pages do): "
         + ", ".join(str(t) for t in (grounding.get("serp_terms") or [])[:30]))
        if grounding.get("serp_terms") else "",
        ("QUESTIONS THE TOP PAGES ANSWER (answer these in the piece): "
         + " | ".join(str(q) for q in (grounding.get("serp_questions") or [])[:8]))
        if grounding.get("serp_questions") else "",
        (f"TARGET LENGTH (roughly match the ranking pages): ~{grounding.get('serp_target_words')} words")
        if grounding.get("serp_target_words") else "",
        "",
        ("FOLLOW THIS OUTLINE (it maps the keywords + gap to sections):\n" + outline) if outline else "",
        ("MATCH THIS BRAND VOICE (a sample of their approved writing — tone/cadence only, do not "
         "copy facts):\n\"\"\"\n" + voice + "\n\"\"\"") if voice else "",
        "",
        f"Task: {spec}",
    ]
    return "\n".join(p for p in parts if p != "")


# Marquee long-form assets get the best model; short/structured assets stay on the mid tier.
_ASSET_TIER = {"article": "full", "faq": "full", "bio": "full", "white_paper": "full"}


def _generate_one(biz: dict, wo: dict, asset_type: str, grounding: Optional[dict] = None,
                  outline: str = "", voice: str = "", license_policy: str = "",
                  regulated_financial: bool = False) -> str:
    tier = _ASSET_TIER.get(asset_type, "mid")
    # Size the output cap to the piece's target length (+ headroom for headings/citations/byline), so a
    # long-form asset isn't truncated mid-draft. A flat 2600 clipped deep_article (2.5k words ~3.3k
    # tokens) and long white_papers. ~1.5 tokens/word; clamp so short types stay cheap, long stay whole.
    # The model reliably writes ~2x its target length, and max_tokens is a CAP (no cost unless used),
    # so size generously: ~2.5 tokens/target-word + a high floor, clamped. Undersizing truncates the
    # draft mid-sentence; oversizing is free.
    target_words = _BRIEF_WORDS.get(asset_type, 1200)
    max_tokens = max(3200, min(int(target_words * 2.5) + 800, 6500))
    return llm.orchestrator_text(_gen_system(license_policy, regulated_financial),
                                 _gen_prompt(biz, wo, asset_type, grounding, outline=outline, voice=voice),
                                 max_tokens=max_tokens, tier=tier)


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
    # A rewrite is ~as long as the input, so the output cap MUST scale with the body. A fixed 2200
    # silently truncated (-> empty) any revision of a 9k+ char article, so _maximize_geo AND the
    # readability pass discarded every long-form revision and never actually improved it. Size to the
    # body (~3 chars/token) + headroom, clamped so long-form isn't truncated but a cap still exists.
    max_tokens = max(2600, min(int(len(body or "") / 3.0) + 500, 8000))
    # creative rewrite -> mid tier (Sonnet/gpt-4o).
    return llm.orchestrator_text(REVISE_SYSTEM, user, max_tokens=max_tokens, tier="mid")


# ----------------------------------------------------------------------------
# Compliance gate (first-class)
# ----------------------------------------------------------------------------
# The UNIVERSAL deceptive-claims screener -- applies to EVERY tenant (FTC truth-in-advertising, not
# securities/insurance rules). A generic (non-finance) tenant gets ONLY this, so finance vocabulary
# (broker-dealer, guaranteed returns) never colours a dentist's or SaaS's compliance screen.
UNIVERSAL_DECEPTIVE_SYSTEM = (
    "You are a truthful-marketing compliance screener. Review the content and return STRICT JSON only: "
    "{\"pass\": bool, \"flags\": [strings]}. Flag any of: demonstrably FALSE or misleading factual "
    "claims; unverifiable superlatives ('best', '#1', 'the leading', 'guaranteed results') stated as "
    "objective fact; testimonials or outcomes presented as typical without context; fabricated "
    "statistics, credentials, or endorsements. Do NOT demand industry-specific regulatory disclosures "
    "-- this is the universal deceptive-claims screen; any vertical-specific rules are applied "
    "separately where they apply. Pass ordinary, accurate, well-sourced marketing content."
)

# The FINANCE screener -- selected ONLY for a regulated-finance tenant (compliance_packs contains
# "financial"). Reproduces the pilot's exact finance screen; a generic tenant never receives it.
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


def _is_financial_pack(profile: dict | None) -> bool:
    """True when the tenant's StrategyProfile carries the finance compliance pack. This -- NOT the
    regulatory_profile firm_type -- is what turns the finance screener/rules ON. Fail-safe: a None
    profile is treated as GENERIC (no finance pack), so an un-threaded caller never gets finance rules
    on a generic tenant. (regulatory_profile.firm_type still sub-specializes WITHIN the finance pack.)"""
    return bool(profile and "financial" in (profile.get("compliance_packs") or []))


def _compliance_system(reg: dict | None, profile: dict | None = None) -> str:
    """The LLM compliance screener prompt for a tenant. A GENERIC tenant gets the UNIVERSAL
    deceptive-claims screener; a regulated-finance tenant (financial compliance pack) gets the finance
    screener + firm-type sub-rules + required disclosures. `reg` is the regulatory_profile (firm_type /
    disclosures); `profile` is the StrategyProfile that gates the pack on/off."""
    if not _is_financial_pack(profile):
        return UNIVERSAL_DECEPTIVE_SYSTEM
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


# Hard prohibitions, matched deterministically. Unlike the LLM screen these cannot be talked out of
# their verdict by a hostile/garbled draft, so a hit here is AUTHORITATIVE. Split into two sets:
#  - UNIVERSAL (FTC truth-in-advertising) applies to EVERY tenant.
#  - FINANCIAL (securities/insurance marketing) applies ONLY to a regulated-finance tenant, so a
#    generic tenant's legitimate copy ("risk-free trial", "guaranteed results or your money back")
#    isn't falsely failed.
_UNIVERSAL_RULES: list[tuple[str, str]] = [
    (r"\b(?:#\s?1|number[-\s]one|the\sbest|best[-\s]in[-\s]class)\b",
     "unverifiable superlative (#1 / best)"),
]
_FINANCIAL_RULES: list[tuple[str, str]] = [
    (r"\bguarantee[ds]?\b[^.\n]{0,40}\b(returns?|profits?|income|results?|gains?|growth)\b",
     "implies guaranteed returns/results"),
    (r"\b(risk[-\s]?free|no[-\s]?risk|zero[-\s]?risk)\b", "claims risk-free"),
    (r"\b\d{1,3}\s?%[^.\n]{0,30}\b(guaranteed|returns?|profits?|gains?)\b",
     "specific performance promise"),
]
_UNIVERSAL_PATTERNS = [(re.compile(p, re.I), msg) for p, msg in _UNIVERSAL_RULES]
_FINANCIAL_PATTERNS = [(re.compile(p, re.I), msg) for p, msg in _FINANCIAL_RULES]


_NEGATION_RE = re.compile(r"\b(no|not|never|without|none|don'?t|do not|cannot|can'?t|are ?n'?t|is ?n'?t|"
                          r"n'?t|makes? no|make no|zero)\b", re.I)


def _deterministic_compliance(body: str, *, regulated_financial: bool = False) -> list[str]:
    """Non-LLM, non-prompt-injectable hard-rule screen. The UNIVERSAL rules (unverifiable '#1'/'best'
    superlatives) run for every tenant; the FINANCIAL rules (guaranteed returns, risk-free, specific
    performance promises) run ONLY for a regulated-finance tenant, so a generic tenant's 'risk-free
    trial' isn't falsely failed. Fail-safe default (regulated_financial=False) = universal-only.
    Returns the list of triggered-rule descriptions (empty == nothing tripped). A match immediately
    preceded by a NEGATION ('no guarantees of income', 'we do not guarantee returns', 'no guaranteed
    returns') is a compliant DISCLAIMER, not a violation -- skip it (this was falsely failing the exact
    disclosure language compliance requires)."""
    text = body or ""
    patterns = _UNIVERSAL_PATTERNS + (_FINANCIAL_PATTERNS if regulated_financial else [])
    flags: list[str] = []
    for pat, msg in patterns:
        for m in pat.finditer(text):
            if _NEGATION_RE.search(text[max(0, m.start() - 28):m.start()]):
                continue   # negated -> disclaimer, not a violation
            flags.append(msg)
            break
    return list(dict.fromkeys(flags))


def _compliance(body: str, system: Optional[str] = None, *, is_reply: bool = False,
                regulated_financial: bool = False) -> dict:
    # Deterministic, non-injectable screen first -- its verdict is authoritative. The finance hard rules
    # run only for a regulated-finance tenant (regulated_financial); universal rules always.
    det_flags = _deterministic_compliance(body, regulated_financial=regulated_financial)
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
    # profile-adapted prompt from _compliance_system; fall back to the UNIVERSAL screen (not the
    # finance one) so a caller that omits `system` never finance-screens a generic tenant.
    res = llm.orchestrator_json(system or UNIVERSAL_DECEPTIVE_SYSTEM, json.dumps({"content": body}), tier="cheap")
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


# A COMPLETE [INSERT ...] token, which may span multiple lines (a common Opus habit -- the opener and
# the closing ']' land on different lines). DOTALL so `.`/[^]] cross newlines up to the first ']'.
_INSERT_TOKEN_RE = re.compile(r"\[INSERT\b[^\]]*\]", re.I | re.S)
_INSERT_OPEN_RE = re.compile(r"\[INSERT\b", re.I)


def _strip_placeholders(body: str) -> str:
    """Publish-ready GUARANTEE: remove any [INSERT: ...] marker the writer still left despite the
    prompt. Remove COMPLETE tokens first (incl. multi-line ones, so no tail line survives), then per
    line: drop a bullet/label line that existed only to carry the placeholder, drop just the SENTENCE
    for an inline leftover, and clean an orphan closing bracket left by a removed multi-line token.
    Idempotent + safe on content with no markers."""
    if not body or "[INSERT" not in body.upper():
        return body
    body = _INSERT_TOKEN_RE.sub("", body)   # complete tokens, even across newlines
    out_lines: list[str] = []
    for line in body.split("\n"):
        if _INSERT_OPEN_RE.search(line):    # a leftover UNCLOSED opener on this line
            without = _INSERT_OPEN_RE.sub("", line)
            core = re.sub(r"^[\s>#|*\-]+", "", without)
            core = re.sub(r"^\*\*[^*]*\*\*\s*[:：]?\s*", "", core).strip(" :|*-—–\t")
            if len(core) < 25:
                continue
            line = " ".join(s for s in re.split(r"(?<=[.!?])\s+", line)
                            if not _INSERT_OPEN_RE.search(s)).strip()
            if not line:
                continue
        if line.count("]") > line.count("["):   # orphan ']' / ']*' from a removed multi-line token
            line = re.sub(r"\s*\][*_]*\s*$", "", line)
        if _dangling_after_strip(line):         # empty list-item value / lone emphasis marker left over
            continue
        out_lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()


def _dangling_after_strip(line: str) -> bool:
    """True for a line left DANGLING once a placeholder was removed -- a list item whose value is now
    empty ('- **Broker-dealer:** ') or a lone emphasis marker ('**'). Deliberately narrow (list items
    + stray markers only) so it NEVER drops a legit section-intro label like '**What the team does:**'."""
    s = line.strip()
    if not s:
        return False
    if re.fullmatch(r"[*_]{1,3}", s):           # lone '**' / '*' / '__'
        return True
    m = re.match(r"^[-*+]\s+(.*)$", s)          # must be a list item
    if not m:
        return False
    rest = re.sub(r"^\*{1,2}[^*]+\*{1,2}\s*[:：]?\s*", "", m.group(1))   # strip a leading bold label:
    return len(rest.strip(" *_:|—–-\t")) == 0


# Owner policy: 'license number' must not appear in content at all. The writer keeps slipping it in as
# a verification search-field ("search by name or license number") despite the prompt, so enforce it
# deterministically: drop it as an "... or license number" alternative, then generalize any standalone
# remainder to "license status".
_LICNUM_ALT_RE = re.compile(
    r"\s*,?\s+(?:and\s*/\s*or|and|or)\s+(?:the\s+|an?\s+)?(?:agent'?s?\s+|individual\s+|their\s+)?"
    r"licen[sc]e\s+numbers?", re.I)
_LICNUM_RE = re.compile(r"\blicen[sc]e\s+numbers?\b", re.I)


_NEG_DISAMBIG_RE = re.compile(
    r"\b(not to be confused with|should not be confused|do not confuse\b|"
    r"not affiliated with (?:the |any )|has no (?:affiliation|connection|association) with (?:the |any ))", re.I)


def _scrub_negative_disambiguation(body: str) -> str:
    """Deterministic backstop for the no-negative-disambiguation policy: drop any SENTENCE that
    contains 'not to be confused with …', 'do not confuse …', 'not affiliated with the …' etc. Those
    name/associate other entities (poor marketing). The prompt ban is the primary lever; this catches
    what the full/Opus tier occasionally leaves. Idempotent; no-op when the markers are absent."""
    if not body or not _NEG_DISAMBIG_RE.search(body):
        return body
    out = []
    for line in body.split("\n"):
        if not _NEG_DISAMBIG_RE.search(line):
            out.append(line)
            continue
        sents = re.split(r"(?<=[.!?])\s+", line)
        kept = " ".join(s for s in sents if not _NEG_DISAMBIG_RE.search(s)).strip()
        out.append(kept)   # keep the non-offending sentences on the line (may be empty)
    return "\n".join(out)


def _scrub_license_phrasing(body: str, profile: Optional[dict] = None) -> str:
    """Remove any 'license number' reference from content -- ONLY for a tenant whose profile SUPPRESSES
    specific credential numbers (a regulated-finance client). For a generic tenant (profile that does
    NOT suppress) this is a NO-OP: a plumber, electrician, or attorney MAY publish their license number.
    Fail-safe: profile None (an un-threaded caller) => run the scrub, preserving today's behavior.
    Idempotent; safe on content that has none."""
    if profile is not None and not profile.get("suppress_specific_credential_numbers"):
        return body
    if not body or "licen" not in body.lower():
        return body
    body = _LICNUM_ALT_RE.sub("", body)
    return _LICNUM_RE.sub("license status", body)


# 'Last updated'/'Last reviewed' label + an OPTIONAL real 'Month YYYY' after it. Group 2 present ==
# already dated; absent == the writer left the date blank (e.g. '*Last updated: *') and we must fill it.
_FRESH_RE = re.compile(r"last[ \t]+(?:updated|reviewed)[ \t]*[:\-]?[ \t]*(\*{0,2})([A-Za-z]+[ \t]+\d{4})?", re.I)


def _ensure_freshness(body: str, when: str) -> str:
    """Guarantee a visible 'Last updated: <Month Year>' line WITH a real date -- an AEO freshness
    signal (citations ~2x more likely when content looks current). The full tier often omits it or
    leaves the date blank, so: fill a dateless 'Last updated:' line, else inject one under the first
    H1 (or prepend). `when` = current 'Month YYYY'."""
    if not body:
        return body
    m = _FRESH_RE.search(body)
    if m:
        # Normalize the date to the REAL current month/year -- fills a blank one AND corrects a wrong/
        # stale date the writer sometimes invents (e.g. 'January 2025'), since 'last updated' must equal
        # when this content was actually produced. Preserves any '*' emphasis after the colon.
        return body[:m.start()] + f"Last updated: {when}{m.group(1)}" + body[m.end():]
    line = f"*Last updated: {when}*"
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("# "):
            lines[i : i + 1] = [ln, "", line]
            return "\n".join(lines)
    return line + "\n\n" + body


def _ensure_readability(body: str, asset_type: str, sq: str, content_type: str,
                        business_name: str, geo: str) -> str:
    """Plain-language backstop. The full/Opus tier writes at ~grade 15 regardless of the prompt AND of
    the GEO fluency signal (a draft already clearing _maximize_geo's target never gets its readability
    revised). Dense prose reads generic and lifts poorly (Princeton fluency +29%; NN/g concise copy
    +58% usability). So if the reading grade is too high, revise ONCE to shorten sentences + simplify
    wording, preserving every fact, citation, quote, heading, the answer-first opener, byline, and
    freshness line. Keeps the rewrite only if it lowered the grade without materially dropping GEO.
    Best-effort; returns the input unchanged on failure/non-improvement."""
    if not body:
        return body
    try:
        from . import content_quality as _cq
    except Exception:  # noqa: BLE001
        return body
    limit = 13 if asset_type in ("white_paper", "deep_article") else 11   # white papers read denser
    try:
        grade = _cq.readability_score(body).get("grade") or 0
    except Exception:  # noqa: BLE001
        return body
    if grade <= limit:
        return body
    rev = _revise(body, [
        f"PLAIN-LANGUAGE REWRITE. The reading level is grade {grade}; bring it to grade 6-8 (and never "
        f"above {limit}). Shorten sentences to ~15-20 words on average, split long/compound sentences, "
        "use everyday words, and write in active voice. PRESERVE EVERYTHING ELSE EXACTLY: keep every "
        "fact, every statistic and its source, every inline citation link, every quotation, all "
        "headings, the answer-first opening paragraph, the byline line, and the 'Last updated' line. Do "
        "NOT drop content, weaken specificity, add [INSERT] placeholders, or change any numbers. Necessary "
        "domain terms (e.g. 'insurance', 'retirement') are fine; simplify the sentences around them."])
    if not rev:
        return body
    rev = _strip_placeholders(rev)
    try:
        g2 = _cq.readability_score(rev).get("grade")
        _kw = dict(target_query=sq, content_type=content_type, asset_type=asset_type,
                   business_name=business_name, geo=geo)
        before = _cq.geo_score(body, **_kw).get("score") or 0
        after = _cq.geo_score(rev, **_kw).get("score") or 0
    except Exception:  # noqa: BLE001
        return body
    if g2 is not None and g2 < grade and after >= before - 3:   # improved readability, GEO held
        return rev
    return body


def _slugify(text: str) -> str:
    return _tu.slugify(text)   # canonical impl in textutils (shared with content_batch's cluster slugs)


_FOOTER_RE = re.compile(
    r"^(?:"
    r"#{1,6}\s+.*(?:disclaimer|disclosure|legal|important notice|not (?:financial|investment|tax|legal) advice).*"  # heading
    r"|-{3,}"                                                                                                       # HR rule
    r"|[*_]{0,3}\s*(?:disclaimer|disclosure|important notice|legal notice|not (?:financial|investment|tax|legal) advice)\b.*"  # bold/plain line
    r")\s*$", re.I | re.M)


def _insert_before_footer(body: str, block: str) -> str:
    """Splice `block` in just BEFORE a trailing legal/disclaimer footer (a disclaimer heading or an
    '---' rule in the last ~60% of the page), so related-content links don't land AFTER the required
    final disclaimer block. Appends if no footer is detected."""
    last = None
    for m in _FOOTER_RE.finditer(body):
        last = m
    if last and last.start() > len(body) * 0.4:
        return body[:last.start()].rstrip() + block + "\n\n" + body[last.start():]
    return body.rstrip() + block


def _add_cluster_links(body: str, cluster: dict | None) -> str:
    """Topic-cluster internal linking. Research (HubSpot): more internal links between related pages
    lift rankings + build the topical authority AI answer engines reward. Deterministically add the
    pillar<->spoke cross-links so a generated cluster reads as ONE connected hub, not isolated pages:
    a PILLAR gets an 'Explore this guide' list linking each spoke; a SPOKE gets a link back UP to the
    pillar. Slug-based relative URLs ('/slug') resolve on the business's site at publish (the publisher
    can rewrite to real URLs). Best-effort; idempotent; skipped without a cluster."""
    if not body or not isinstance(cluster, dict):
        return body
    role = cluster.get("role")
    if role == "spoke" and cluster.get("pillar_title"):
        ptitle = cluster["pillar_title"]
        pslug = cluster.get("pillar_slug") or _slugify(ptitle)
        if f"](/{pslug})" not in body:   # precise: the exact markdown link, not a bare slug substring
            body = _insert_before_footer(body, f"\n\n*Part of our complete guide: [{ptitle}](/{pslug}).*\n")
    elif role == "pillar":
        spokes = [s for s in (cluster.get("spokes") or []) if isinstance(s, dict) and s.get("title")][:8]
        if spokes and "## Explore this guide" not in body:
            items = "\n".join(f"- [{s['title']}](/{s.get('slug') or _slugify(s['title'])})" for s in spokes)
            body = _insert_before_footer(body, f"\n\n## Explore this guide\n\n{items}\n")
    return body


_BYLINE_RE = re.compile(r"^\s*[*_]{0,2}\s*(?:by |written by |author\b|reviewed by )", re.I | re.M)


def _ensure_byline(body: str, business_name: str, reviewer: str = "editorial team") -> str:
    """E-E-A-T authorship signal. For YMYL content Google's rater guidelines rate a page with no clear
    author background 'Lowest', and named authorship is a top measured citation signal (+30.6%
    correlation, Semrush). Add a general, compliance-safe byline/reviewer line under the H1 -- truthful
    given the human review-before-publish workflow, and NEVER a specific person or license number. The
    reviewer NOUN is profile-driven (`byline_reviewer`): 'editorial team' by default, 'licensed
    professionals' for finance, 'a licensed attorney'/'a licensed clinician' for legal/medical, etc.
    Best-effort; skipped if a byline already exists or the business name is unknown."""
    if not body or not (business_name or "").strip() or _BYLINE_RE.search(body):
        return body
    name = business_name.strip()
    reviewer = (reviewer or "editorial team").strip()
    # byline_reviewer may be a bare noun ('editorial team', 'licensed professionals') -> possessive,
    # or article-prefixed ('a licensed attorney', 'a licensed clinician') -> drop the possessive so the
    # grammar reads right ("Reviewed by a licensed attorney", not "Reviewed by X's a licensed attorney").
    if reviewer.lower().startswith(("a ", "an ", "the ")):
        review_part = f"Reviewed by {reviewer}"
    else:
        review_part = f"Reviewed by {name}’s {reviewer}"
    line = f"*By {name} · {review_part}*"
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("# "):
            lines[i : i + 1] = [ln, "", line]
            return "\n".join(lines)
    return line + "\n\n" + body


def _scoring_query(wo: dict, business_name: str = "", geo: str = "") -> str:
    """A REAL user query for AEO/GEO scoring + optimization. The gap model's topic is an internal LABEL
    ('Entity Disambiguation Asset: ...', 'Legitimacy & Transparency Hub page') whose scaffolding words
    ('asset', 'page', 'hub') never appear in natural copy -- so scoring answer-first against it
    auto-fails. Strip the label wrapper and anchor with the business name + city, which the content
    always contains, so the citability checks map to what a reader/AI actually asks."""
    tq = (wo.get("target_query") or (wo.get("gap_specifics") or {}).get("source_query")
          or wo.get("title") or "").strip()
    q = re.sub(r"\([^)]*\)", " ", tq)                                          # drop parentheticals (URLs)
    q = re.sub(r"^.*?\b(?:asset|page|section|hub|brief|doc(?:ument)?)\b\s*[:\-–—]\s*", "", q, flags=re.I)
    q = re.sub(r"\b(?:asset|section|hub|brief|landing\s+page|document|page)\b", " ", q, flags=re.I)  # stray label words
    q = re.sub(r"[\"'“”:]+", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" -–—&")
    if business_name and business_name.lower() not in q.lower():
        q = f"{business_name} {q}".strip()
    city = (geo or "").split(",")[0].strip()
    if city and city.lower() not in q.lower():
        q = f"{q} {city}".strip()
    return q or (f"{business_name} {city}".strip() or tq)


def _maximize_geo(body: str, sq: str, content_type: str, asset_type: str,
                  business_name: str, geo: str, *, target: int = 75, rounds: int = 2) -> str:
    """AI-FIRST optimization: iteratively revise the draft to MAXIMIZE its GEO (AI-citability) grade --
    the whole point of this content is to be surfaced + CITED by AI answer engines, so we optimize
    directly against the GEO scorer. Each round revises the currently-weak signals (answer-first
    openers, question headings, attributable stats, inline authoritative citations, FAQ, chunking) and
    keeps the higher-scoring version; stops at `target` or when a round doesn't improve. Best-effort:
    returns the input unchanged on any failure or non-improvement."""
    try:
        from . import content_quality as _cq
    except Exception:  # noqa: BLE001
        return body
    best = body or ""
    try:
        best_g = _cq.geo_score(best, target_query=sq, content_type=content_type, asset_type=asset_type,
                               business_name=business_name, geo=geo)
    except Exception:  # noqa: BLE001
        return body
    for _ in range(max(1, rounds)):
        if (best_g.get("score") or 0) >= target:
            break
        weak = [c for c in best_g.get("checks", []) if not c.get("ok") and c.get("fix")]
        if not weak:
            break
        rev = _revise(best, [
            "PRIMARY GOAL: make this content maximally CITABLE by AI answer engines (ChatGPT, "
            "Perplexity, Gemini, Google AI Overviews). Apply each fix below WITHOUT fabricating facts "
            "or statistics, changing the meaning, adding [INSERT] placeholders, or keyword-stuffing. "
            "Use only real, attributable numbers (industry/official sources you can name) and inline "
            "links to authoritative primary sources (.gov/.edu/official). Keep the answer-first opener:"
        ] + [f"{c.get('label')}: {c.get('fix')}" for c in weak])
        if not rev:
            break
        rev = _strip_placeholders(rev)   # the revision must not (re)introduce placeholders
        try:
            g = _cq.geo_score(rev, target_query=sq, content_type=content_type, asset_type=asset_type,
                              business_name=business_name, geo=geo)
        except Exception:  # noqa: BLE001
            break
        if (g.get("score") or 0) > (best_g.get("score") or 0):
            best, best_g = rev, g
        else:
            break   # no improvement -> stop iterating
    return best


# UNIVERSAL compliance-fix editor -- used for every generic tenant. Strips deceptive claims only; no
# finance/broker-dealer/disclosure vocabulary.
_COMPLIANCE_FIX_UNIVERSAL_BASE = (
    "You are a marketing-claims compliance editor. Revise the content to RESOLVE the listed compliance "
    "issues while preserving the accurate, helpful message. REMOVE false or misleading claims, "
    "unverifiable superlatives ('best'/'#1'/'the leading' stated as fact), and any 'guaranteed results' "
    "promise. Do NOT fabricate facts, and do NOT use [INSERT: ...] placeholders -- write around anything "
    "you don't have with accurate general wording. Put any added disclaimer in ONE short block at the "
    "very END of the content -- NEVER before the page's opening answer, and keep that answer-first "
    "opening intact. Do NOT hedge every fact or add editor-facing notes ('before publication...', "
    "'verify before publishing'). Output ONLY the revised content, no preamble."
)

# FINANCE compliance-fix editor -- used ONLY for a regulated-finance tenant.
_COMPLIANCE_FIX_BASE = (
    "You are a financial-services compliance editor. Revise the content to RESOLVE the listed "
    "compliance issues while preserving the accurate, helpful message. REMOVE prohibited claims "
    "(guaranteed/implied returns, performance promises, 'risk-free', unverifiable superlatives "
    "like 'best'/'#1' stated as fact). ADD any missing required disclosures -- e.g. the "
    "broker-dealer / representative relationship where financial products are marketed, and that "
    "any testimonials are individual experiences and not typical results. Do NOT fabricate facts, "
    "and do NOT use [INSERT: ...] placeholders or add specific license numbers -- write around "
    "anything you don't have with accurate general wording (e.g. 'the affiliated broker-dealer'). "
    "Put ALL added disclosures/disclaimers in ONE short block at the very END of the content -- NEVER "
    "before the page's opening answer, and keep that answer-first opening intact. Do NOT hedge every "
    "fact or add editor-facing notes ('before publication...', 'verify before publishing'). Output "
    "ONLY the revised content, no preamble."
)


def _compliance_fix_system(license_policy: str = "", regulated_financial: bool = False) -> str:
    """The compliance-autofix editor prompt for ONE tenant. A generic tenant gets the UNIVERSAL editor
    (deceptive-claims only); a regulated-finance tenant gets the finance editor (broker-dealer /
    disclosure rules). `license_policy` = the profile-driven license ban ('' for generic).
    NO_NEGATIVE_DISAMBIGUATION stays agnostic + always present. The `COMPLIANCE_FIX_SYSTEM` alias =
    this with NO license + the universal editor (the finance-free default)."""
    base = _COMPLIANCE_FIX_BASE if regulated_financial else _COMPLIANCE_FIX_UNIVERSAL_BASE
    return base + license_policy + llm.NO_NEGATIVE_DISAMBIGUATION_POLICY


COMPLIANCE_FIX_SYSTEM = _compliance_fix_system()   # finance-free GENERIC alias (universal editor)


def _compliance_autofix(biz: dict, body: str, flags: list, reg: Optional[dict] = None,
                        license_policy: str = "", regulated_financial: bool = False) -> Optional[str]:
    """Attempt to make a flagged draft compliant: strip prohibited claims + insert the missing
    disclosures (using what we know about the business + its regulatory profile). A generic tenant gets
    the universal editor and no broker-dealer-disclosure instruction; a regulated-finance tenant gets
    the finance editor + firm-type framing. Returns the revised body, or None. The caller re-screens
    the result -- this never decides compliance."""
    reg = reg or {}
    ft = (reg.get("firm_type") or "").lower()
    disc = reg.get("disclosures") or []
    reg_line = ""
    # Firm-type / broker-dealer framing is finance-only; a generic tenant never gets it.
    if regulated_financial and ft:
        reg_line = f"Firm type: {ft}. "
        if ft == "non_financial":
            reg_line += "Do NOT add any financial/broker-dealer disclosures. "
    # Required disclosures a tenant explicitly persisted apply regardless of vertical.
    if disc:
        reg_line += "Use ONLY these required disclosures (verbatim where possible): " + "; ".join(str(d) for d in disc) + ". "
    ctx = (
        f"Business: {biz.get('name', '')} -- services: {biz.get('services', '')}.\n"
        f"{reg_line}\n"
        f"Narratives working against them (context only): {biz.get('contested_terms', '')}.\n"
        "Compliance issues to resolve:\n- " + "\n- ".join(str(f) for f in (flags or []))
        + f"\n\nContent to revise:\n{body}"
    )
    revised = llm.orchestrator_text(_compliance_fix_system(license_policy, regulated_financial),
                                    ctx, max_tokens=2400, tier="mid")
    return (revised or "").strip() or None


# ----------------------------------------------------------------------------
# Orchestrated generation for a work order
# ----------------------------------------------------------------------------
def generate_for_wo(business_id: int, wo: dict, biz: dict,
                    content_type: Optional[str] = None, batch_id: Optional[int] = None) -> Optional[int]:
    # Rich-media capabilities bypass the single-source LLM path and go to rich_media_generator,
    # which assembles multi-source corpus context (audit answers, gap model, competitor data) and
    # uses the NotebookLM API or its in-house LLM fallback. Output lands in rich_media_drafts as
    # pending_review (same human gate). Dormant-safe: rich_media_generator self-creates its table
    # and falls back to the LLM when no NotebookLM/Gemini key is set. (batch_id/content_type don't
    # apply to rich-media pieces — they're not part of the gap batch's content-type spread.)
    cap = (wo.get("capability") or "").lower()
    if cap in _RICH_MEDIA_CAP_MAP:
        topic = wo.get("title", "")
        if _already_covered(business_id, topic):
            log.info("WO '%s' already covered (pgvector); skipping.", topic)
            return None
        try:
            from . import rich_media_generator as _rmg
        except ImportError:  # pragma: no cover -- loose-script fallback
            import rich_media_generator as _rmg  # type: ignore
        # When the user picked ONE specific rich type (Create Content), generate ONLY that — not the
        # cap's full spread. Otherwise deep_content emits deep_article+blog_series+newsletter for a
        # single 'newsletter' request (3 drafts + 3x spend, selection ignored).
        _ct = (content_type or "").lower()
        rm_types = [_ct] if _ct in _RICH_MEDIA_CAP_MAP[cap] else _RICH_MEDIA_CAP_MAP[cap]
        # Steer rich media to what THIS work order is about. A custom "Create content" WO puts the
        # user's real focus in `instruction`; a STRATEGY-generated WO puts a developer signature there
        # ("rich_media_generator.generate([...]): ...") which must NOT become the piece's focus OR leak
        # into its title. Use the instruction only when it's a real focus, else None so the generator
        # synthesizes from the corpus and titles the piece by its type.
        _instr = (wo.get("instruction") or "").strip()
        if "rich_media_generator.generate(" in _instr or _instr.startswith("rich_media_generator"):
            _instr = ""
        rm_topic = _instr or None
        ids = _rmg.generate(business_id, rm_types, topic=rm_topic)
        log.info("WO %s (cap=%s) -> rich_media_generator(%s): created %s",
                 wo.get("wo_code") or wo.get("wo_id"), cap, rm_types, ids)
        return ids[0] if ids else None

    # Prefer the EXPLICIT content_type the user picked (Create Content) over title-keyword guessing.
    # TITLE_HINTS mis-routed 'Blog post: ...' -> gbp_post (80-150w GBP post) and flipped on stray
    # words in the description; an explicit content_type resolves the asset_type deterministically.
    asset_type = _CT_ASSET_OVERRIDE.get((content_type or "").lower()) or _asset_type_for(wo)
    if not asset_type:
        log.info("WO %s not a generatable content type; skipping.", wo.get("wo_code") or wo.get("wo_id"))
        return None
    # content_type is the richer label used for GEO weighting + impact grouping (blog / white_paper /
    # landing_page / local_page / social ...). Falls back to the wo's own content_type, then asset_type.
    content_type = content_type or wo.get("content_type") or asset_type
    topic = wo.get("title", "")
    if _already_covered(business_id, topic):
        log.info("WO '%s' already covered (pgvector); skipping.", topic)
        return None

    # Scope keywords to this piece. Batch pieces set target_query; plan work orders don't, so fall
    # back to their gap query / title so single-draft pieces also get on-topic keywords, not the
    # business-wide top-15.
    _scope_q = wo.get("target_query") or (wo.get("gap_specifics") or {}).get("source_query") or wo.get("title")
    grounding = _grounding_context(business_id, target_query=_scope_q, biz=biz)
    # SERP-competitor benchmark (Phase 3): the shared terms + word-count target from the pages
    # actually ranking for this query, so the draft can be graded "vs. the competition" rather than
    # absolute. Dormant-safe: {skipped} with no SERPER_API_KEY, and never raises.
    serp_bench = None
    try:
        from . import serp_benchmark as _sb
        _tq = wo.get("target_query") or topic
        if _tq:
            b = _sb.benchmark(_tq)
            if b and not b.get("skipped"):
                serp_bench = b
                grounding["serp_terms"] = b.get("terms", [])[:30]
                grounding["serp_questions"] = b.get("questions", [])[:8]
                grounding["serp_target_words"] = b.get("avg_word_count")
    except Exception as e:  # noqa: BLE001 -- benchmark is best-effort, never blocks generation
        log.debug("serp benchmark skipped: %s", e)
    # (NeuronWriter removed from the stack.) SERP coverage now comes from serp_benchmark above
    # (grounding["serp_terms"/"serp_questions"/"serp_target_words"]), which _gen_prompt feeds the writer.
    neuron = {}
    voice = _brand_voice(business_id)
    # If the owner cloned a brand writing style (from a URL), prepend it so the draft matches that
    # voice. Best-effort — never blocks generation.
    try:
        from . import writing_style as _ws
        _style = _ws.active_profile(business_id)
        if _style:
            voice = (f"BRAND WRITING STYLE — match this voice exactly: {_style}\n\n" + (voice or "")).strip()
    except Exception as e:  # noqa: BLE001
        log.debug("writing-style voice unavailable: %s", e)
    # Brand rules + the owner's uploaded source material -> AUTHORITATIVE (absolute rules + real
    # client facts), injected as grounding (NOT `voice`, which is tone-only). Three fidelity fixes:
    #  - TOPIC-SCOPED grounding (grounding_retrieval.facts_block) so the piece gets the facts relevant
    #    to ITS topic, not just the newest 4.5k tokens of the corpus (falls back to the recency corpus
    #    only when the topic matches nothing);
    #  - imperative RULES inside uploaded docs ("always/never/include ...") are lifted out + obeyed;
    #  - FAIL-LOUD: a real grounding read error must NOT silently ship off-brand/ungrounded content, so
    #    we re-raise (the job fails + retries) instead of swallowing it.
    try:
        from . import source_material as _sm
        from . import grounding_retrieval as _gr
        _rules = _sm.guardrails(business_id)
        _doc_rules = _sm.instruction_rules(business_id)
        _topic_facts = _gr.facts_block(business_id, _scope_q)
        _facts = _topic_facts or _sm.corpus(business_id, max_tokens=3500)
        _cm_parts = []
        if _rules:
            _cm_parts.append("BRAND RULES — these are ABSOLUTE and override anything else:\n" + _rules)
        if _doc_rules:
            _cm_parts.append("MUST-FOLLOW RULES FROM THE CLIENT'S UPLOADED MATERIAL (ABSOLUTE — obey "
                             "these exactly):\n" + _doc_rules)
        if _facts:
            _cm_parts.append("SOURCE MATERIAL — the client's own facts most relevant to THIS topic; "
                             "ground the content in these and do not contradict them:\n" + _facts)
        if _cm_parts:
            grounding["client_material"] = "\n\n".join(_cm_parts)
    except ImportError:  # pragma: no cover -- loose-script fallback
        pass
    except Exception as e:  # noqa: BLE001 -- a REAL read error must fail loud, not ship ungrounded
        log.warning("brand/source grounding read FAILED for business %s -- failing generation so it "
                    "retries with grounding rather than shipping off-brand/ungrounded content: %s",
                    business_id, e)
        raise
    reg = _reg_profile(business_id)          # firm-type-aware compliance (RIA vs BD vs non-financial)
    # Business-agnostic StrategyProfile: load it ONCE and derive everything vertical-specific -- the
    # license ban (spliced into GEN_SYSTEM / the compliance-fix editor), the post-processing scrub gate,
    # and the compliance PACK (universal-only for a generic tenant vs the finance screener + hard rules
    # for a regulated-finance tenant). A generic tenant gets '' (no license ban), no scrub, and the
    # universal deceptive-claims screen. Fail-safe: any error -> generic.
    try:
        from . import business_profile as _bp
        _profile = _bp.for_business(business_id)
        _lic = _bp.license_policy_for(_profile)
    except Exception:  # noqa: BLE001 -- never block generation on the profile lookup
        _profile, _lic = None, ""
    _reg_fin = bool(_profile and _profile.get("regulated_financial"))
    comp_system = _compliance_system(reg, _profile)
    # Pass 1 (long-form): a keyword-mapped outline the draft writes from.
    outline = _outline(biz, wo, asset_type, grounding) if asset_type in ("article", "faq") else ""
    # Pass 2: the grounded draft.
    body = _generate_one(biz, wo, asset_type, grounding, outline=outline, voice=voice,
                         license_policy=_lic, regulated_financial=_reg_fin)
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

    # Pass 4: AI-FIRST optimization -- the PRIMARY objective of this content is to be surfaced + CITED
    # by AI answer engines, so MAXIMIZE the GEO (AI-citability) grade directly against the scorer, using
    # a REAL query (not the internal asset label). SEO/keyword coverage above is the secondary benefit.
    _score_q = _scoring_query(wo, (biz.get("name") if isinstance(biz, dict) else "") or "",
                              (biz.get("geo") if isinstance(biz, dict) else "") or "")
    if asset_type not in ("schema", "social_post", "gbp_post", "x_post", "facebook_post",
                          "instagram_post", "linkedin_post", "pinterest_post"):
        _geo_before = None
        try:
            from . import content_quality as _cqg
            _geo_before = (_cqg.geo_score(body, target_query=_score_q, content_type=content_type,
                           asset_type=asset_type, business_name=(biz.get("name") or ""),
                           geo=(biz.get("geo") or "")) or {}).get("score")
        except Exception:  # noqa: BLE001
            pass
        body = _maximize_geo(body, _score_q, content_type, asset_type,
                             (biz.get("name") if isinstance(biz, dict) else "") or "",
                             (biz.get("geo") if isinstance(biz, dict) else "") or "")

    # compliance gate (profile-adapted: universal for a generic tenant, finance rules for a finance one)
    comp = _compliance(body, system=comp_system, regulated_financial=_reg_fin)
    comp_pass = comp.get("pass")
    comp_flags = comp.get("flags", [])

    # Compliance AUTO-FIX: rather than dumping a flagged draft on the human as "needs_fix", try
    # once to resolve the issues (strip prohibited claims + add the missing disclosures) and
    # re-screen. If it now passes (or is at least no longer a hard fail), keep the fixed version
    # and record WHAT was changed so the human can confirm the added language is accurate.
    highlighted: list = []
    if comp_pass is False and not eval_unavailable:
        fixed = _compliance_autofix(biz, body, comp_flags, reg=reg, license_policy=_lic,
                                    regulated_financial=_reg_fin)
        if fixed and fixed != body:
            recheck = _compliance(fixed, system=comp_system, regulated_financial=_reg_fin)
            if recheck.get("pass") is not False:   # passed, or unknown (no LLM) -> human reviews
                body = fixed
                highlighted = [{"type": "compliance", "note": str(f)} for f in comp_flags]
                comp_pass = recheck.get("pass")
                comp_flags = list(recheck.get("flags", []))

    # Publish-ready guarantee: strip any residual [INSERT] the writer/compliance-fix still left, so the
    # stored draft is publishable as-is (the prompt asks for this, but the full tier occasionally
    # placeholders a regulated specific anyway). Runs AFTER the compliance gate so it also cleans any
    # placeholder a disclosure auto-fix introduced.
    body = _strip_placeholders(body)
    body = _scrub_license_phrasing(body, _profile)
    body = _scrub_negative_disambiguation(body)   # no 'not to be confused with X' — positive identity only
    # De-generic pass: strip the safest formulaic AI-slop lead-ins deterministically ('In conclusion,',
    # 'It's important to note that', 'In today's fast-paced world,'). Buzzwords mid-sentence are left to
    # the prompt ban + revision loop (deleting them blindly would break grammar).
    try:
        from . import content_quality as _cqs
        body = _cqs.scrub_slop(body)
    except Exception:  # noqa: BLE001 -- best-effort cosmetic cleanup, never sink the draft
        pass
    # Guarantee the freshness line the AEO scorer looks for (full tier often omits it despite the prompt).
    if asset_type not in ("schema", "social_post", "gbp_post", "x_post", "facebook_post", "instagram_post"):
        body = _ensure_freshness(body, f"{datetime.now(timezone.utc):%B %Y}")
        # E-E-A-T authorship (YMYL requirement): add a general, compliance-safe byline/reviewer line.
        # The reviewer noun is profile-driven ('editorial team' generic, 'licensed professionals' finance).
        body = _ensure_byline(body, (biz.get("name") if isinstance(biz, dict) else "") or "",
                              reviewer=(_profile.get("byline_reviewer") if _profile else "") or "editorial team")
        # Plain-language backstop: the Opus tier writes grade ~15 despite the prompt + fluency signal,
        # so force a readability rewrite when the grade is too high (preserves facts/citations/quotes).
        body = _ensure_readability(body, asset_type, _score_q, content_type,
                                   (biz.get("name") if isinstance(biz, dict) else "") or "",
                                   (biz.get("geo") if isinstance(biz, dict) else "") or "")
        # Topic-cluster internal linking: cross-link this piece to its pillar/spokes (added LAST so the
        # readability rewrite can't mangle the links). No-op unless the WO carries a `cluster` plan.
        body = _add_cluster_links(body, wo.get("cluster") if isinstance(wo, dict) else None)
    placeholders = _extract_placeholders(body)
    # Exact-content fingerprint (for dedup): stored on the draft, copied to the asset at approval.
    content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()

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
    # Exact-duplicate guard: if this same body already exists (published asset or live draft),
    # FLAG it for the human rather than silently dropping or re-publishing the same page.
    if _duplicate_body(business_id, content_hash):
        status = "needs_fix"
        comp_flags = list(comp_flags) + [
            "exact duplicate of already-drafted/published content -- don't re-publish the same page"]

    # quality_notes carries the rubric eval + the SEO keyword-coverage scorecard (CI-3 UI reads it)
    # + the Wave-2 draft-quality scorers (on-page SEO, citation-readiness, fact-check).
    quality_notes = {**(evaluation or {}), "keyword_coverage": coverage}
    try:
        from . import content_quality as _cq
        _kw = list(coverage.get("covered", [])) + list(coverage.get("missing", []))
        _site = grounding if isinstance(grounding, dict) else None
        # NeuronWriter SERP/NLP terms -> covered-vs-missing term-coverage grade (Rec 1 backend).
        _nterms: list[str] = []
        if isinstance(neuron, dict):
            for _k in ("terms_h2", "terms_basic"):
                _v = neuron.get(_k)
                if isinstance(_v, str):
                    _nterms += [t.strip() for t in _v.replace("\n", ",").split(",") if len(t.strip()) > 2]
        _nterms = list(dict.fromkeys(_nterms))[:40]
        quality_notes.update(_cq.analyze_draft(
            body, target_query=_score_q or wo.get("target_query") or "", keywords=_kw,
            site_summary=_site, with_fact_check=True, neuron_terms=_nterms or None,
            business_name=(biz.get("name") if isinstance(biz, dict) else "") or "",
            geo=(biz.get("geo") if isinstance(biz, dict) else "") or "",
            content_type=content_type, asset_type=asset_type, serp_benchmark=serp_bench,
            business_id=business_id))
    except Exception as e:  # noqa: BLE001 -- quality scoring must never break generation
        # WARNING not debug: if this path fails, citation_ready is absent and the HOLD gate below is
        # silently skipped, so an un-vetted draft is presented as a normal pending_review.
        log.warning("draft quality analysis failed (%s) -- citation-readiness gate will be skipped "
                    "for this draft; flagging it for manual review.", e)
    # Denormalize the GEO grade for cheap querying/sorting (the batch/impact views read it).
    geo_val = None
    try:
        _g = quality_notes.get("geo")
        if isinstance(_g, dict) and isinstance(_g.get("score"), (int, float)):
            geo_val = float(_g["score"])
    except Exception:  # noqa: BLE001
        geo_val = None

    # Phase-3 portfolio grades: where this draft sits in the topic clusters, and concrete in-draft
    # internal-link suggestions to existing owned/site pages. Best-effort -- never blocks generation.
    try:
        from . import topical_authority as _ta, internal_links as _il
        _tq = wo.get("target_query") or ""
        quality_notes["topic_coverage"] = _ta.score_draft_topic_coverage(business_id, body, _tq)
        quality_notes["suggested_links"] = _il.suggest_internal_links_for_draft(business_id, body, _tq)
        # Topic-cluster role/relationships (pillar or spoke, and the sibling pieces) so the review UI +
        # publisher understand the hub structure this piece belongs to.
        if isinstance(wo.get("cluster"), dict):
            _cl = wo["cluster"]
            quality_notes["cluster"] = {"role": _cl.get("role"), "pillar_title": _cl.get("pillar_title"),
                                        "pillar_slug": _cl.get("pillar_slug"),
                                        "spokes": [s.get("title") for s in (_cl.get("spokes") or [])
                                                   if isinstance(s, dict) and s.get("title")]}
    except Exception as e:  # noqa: BLE001
        log.debug("topic/link enrichment skipped: %s", e)

    # Grounding-coverage ADVISORY (warn-only): does the client's verified source corpus hold facts for
    # THIS topic? Pure metadata for the review UI -- NEVER read by any gate and inert to the writer
    # prompt (the piece was already generated with whatever grounding existed). Fail-safe: coverage()
    # reads ONLY grounding_retrieval (never raises) and is a total function, and this block is
    # best-effort, so a failure just omits the key. HARD RULE: never call source_material.* here (those
    # are fail-loud re-raisers and would crash generation).
    try:
        quality_notes["coverage_advisory"] = _gc.coverage(business_id, _scope_q)
    except Exception as e:  # noqa: BLE001
        log.debug("coverage advisory skipped: %s", e)

    # Phase-4 visual content: pull the ![alt](IMAGE: prompt) markers the writer embedded into
    # structured metadata (alt text + prompt + section) so images can be produced per marker.
    try:
        from . import image_extraction as _ie
        quality_notes["image_markers"] = _ie.extract_image_markers(body)
    except Exception as e:  # noqa: BLE001
        log.debug("image marker extraction skipped: %s", e)

    # NeuronWriter draft content-score (the SERP-coverage gauge), stored alongside our own scores so
    # the editor can show both. Free (/evaluate-content). Dormant-safe -- skipped without a key/query.
    try:
        nq = (neuron or {}).get("query")
        if nq:
            from . import neuronwriter as _nw
            sc = _nw.score(nq, body, title=topic)
            if sc.get("content_score") is not None:
                quality_notes["neuron"] = {"content_score": sc["content_score"], "query": nq,
                                           "target": neuron.get("content_score_target")}
    except Exception as e:  # noqa: BLE001
        log.debug("neuronwriter score skipped: %s", e)

    # Citation-readiness gate (the on-page lever that decides whether AI will quote the piece).
    # REVISE-UNTIL-CLEAN: rather than immediately flagging a low-scoring draft, take up to
    # MAX_CITATION_REVISIONS targeted passes to lift it over the bar, re-scoring each time and
    # keeping the change only if it actually improved. Only if it STILL can't clear the bar does the
    # draft get HELD for an author (below) -- the owner should never be handed a draft with issues.
    def _cr_score(qn):
        cr = qn.get("citation_ready")
        return cr.get("score") if isinstance(cr, dict) else None, cr

    if status == "pending_review":
        cr_score, cr = _cr_score(quality_notes)
        cr_rev = 0
        while (isinstance(cr_score, (int, float)) and cr_score < CITATION_READY_MIN
               and cr_rev < MAX_CITATION_REVISIONS and isinstance(cr, dict)):
            tips = [t.get("fix", "") for t in (cr.get("tips") or [])[:4] if isinstance(t, dict) and t.get("fix")]
            fixed = _revise(body, ["Improve how quotable/citable this is for AI answer engines "
                                   "(clear self-contained claims, a direct answer up top, specific "
                                   "facts/stats, clean structure). Apply: " + "; ".join(tips)]) if tips else None
            if not fixed or fixed == body:
                break
            try:
                from . import content_quality as _cq2
                new_cr = _cq2.citation_ready(fixed, wo.get("target_query") or "")
            except Exception:  # noqa: BLE001
                new_cr = None
            new_score = new_cr.get("score") if isinstance(new_cr, dict) else None
            cr_rev += 1
            if isinstance(new_score, (int, float)) and new_score > (cr_score or 0):
                body, cr, cr_score = fixed, new_cr, new_score
                quality_notes["citation_ready"] = new_cr
                revisions += 1
                content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
            else:
                break
        # Still under the bar after all attempts -> HOLD it for an author (don't present a flawed
        # draft). "held" drafts are kept out of the review queue and surfaced separately.
        if isinstance(cr_score, (int, float)) and cr_score < CITATION_READY_MIN:
            status = "held"
            tips = "; ".join(t.get("fix", "") for t in ((cr or {}).get("tips") or [])[:3] if isinstance(t, dict))
            comp_flags = list(comp_flags) + [
                f"citation-readiness {cr_score:.0f}/100 below {CITATION_READY_MIN:.0f} after "
                f"{cr_rev} auto-revision(s) -- needs an author"
                + (f" -- {tips}" if tips else "")]
        elif cr_score is None:
            # Grading didn't produce a citation-readiness score (grader/orchestrator hiccup). Don't
            # present the draft as fully vetted -- flag it so the reviewer knows the gate was skipped.
            comp_flags = list(comp_flags) + ["citation-readiness check unavailable — please review this draft manually"]

    # A draft that couldn't clear quality/compliance is HELD (needs an author), not shown as a
    # ready-to-review draft with issues. "needs_fix" is folded into "held" so the review queue only
    # ever contains clean drafts.
    if status == "needs_fix":
        status = "held"

    # Phase 5C: auto-generate the images the writer marked (![alt](IMAGE: prompt)) and inline their
    # real URLs, with descriptive filenames + alt text (image SEO). Dormant-safe (no provider key ->
    # markers left as-is) and budget-capped. The generated {url, alt} list rides in quality_notes so
    # approve() can emit ImageObject schema for them.
    try:
        import re as _re_img
        from . import visual_content as _vc_img
        if _vc_img.image_configured():
            _imgs: list[dict] = []
            _cap = int(os.getenv("CONTENT_MAX_IMAGES", "3"))

            def _mk_img(m):
                _alt, _p = m.group(1).strip(), m.group(2).strip()
                if len(_imgs) >= _cap or llm.cost.over_budget(business_id):
                    return m.group(0)  # leave the marker; a later run / manual gen can fill it
                try:
                    _r = _vc_img.generate_image(business_id, _p, kind="content_image",
                                                work_order_id=wo.get("_db_id"), alt=_alt or None)
                except Exception:  # noqa: BLE001
                    return m.group(0)
                _u = _r.get("url") if isinstance(_r, dict) else None
                if not _u:
                    return m.group(0)
                _imgs.append({"url": _u, "alt": _alt})
                return f"![{_alt}]({_u})"

            _new = _re_img.sub(r"!\[([^\]]*)\]\(\s*IMAGE:\s*([^)]+)\)", _mk_img, body)
            if _imgs:
                body = _new
                quality_notes["images"] = _imgs
                content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    except Exception as e:  # noqa: BLE001 -- image generation must never break drafting
        log.debug("inline image generation skipped: %s", e)

    _ensure_table()
    with db() as conn:
        row = conn.execute(
            """INSERT INTO content_drafts
               (business_id, work_order_id, asset_type, title, body, target_query,
                quality_score, quality_notes, revision_count, compliance_pass,
                compliance_flags, status, highlighted_sections, placeholders_pending, content_hash,
                batch_id, content_type, geo_score)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (business_id, wo.get("_db_id"), asset_type, topic, body,
             wo.get("target_query"), round(score, 2), json.dumps(quality_notes),
             revisions, comp_pass, json.dumps(comp_flags), status,
             json.dumps(highlighted), json.dumps(placeholders), content_hash,
             batch_id, content_type, geo_val),
        ).fetchone()
        conn.commit()
    # Ledger the estimated LLM spend for this draft (rec 10b) so content generation shows up in COGS
    # and counts against the monthly cap -- previously every drafting call was invisible to the ledger.
    # The passes (outline + draft + 1+revisions full generations + eval/compliance) don't surface
    # provider usage, so this is an estimate (cost.py is explicitly estimate-grade for budgeting).
    try:
        _cm, _ = llm._model_for("mid") if llm.ORCHESTRATOR == "anthropic" else (None, None)
        if _cm is None:
            _, _cm = llm._model_for("mid")
        _passes = 1 + revisions
        _in = llm.cost.approx_tokens(json.dumps(grounding, default=str)) + \
            llm.cost.approx_tokens(outline or topic)
        _out = llm.cost.approx_tokens(body) * _passes + 800  # +eval/compliance/keyword overhead
        llm.cost.record(business_id, None, llm.ORCHESTRATOR, "content_draft", _cm, _in, _out,
                        {"content_type": asset_type, "api": "llm"})
    except Exception as e:  # noqa: BLE001 -- cost logging must never break generation
        log.debug("content cost record skipped: %s", e)
    log.info("Draft %d for '%s' (type=%s, score=%.2f, rev=%d, compliance=%s, status=%s, placeholders=%d)",
             row["id"], topic, asset_type, score, revisions, comp_pass, status, len(placeholders))
    return row["id"]


def generate(business_id: int, only_wo: Optional[int] = None,
             content_type: Optional[str] = None,
             due_within_days: Optional[int] = None) -> list[int]:
    """Generate drafts for the auto content work orders of the latest plan.
    Pulls work orders from the tracking table if present, else from the plan JSON.

    due_within_days (JIT, Phase 3): when set, generate ONLY content pieces whose cadence slot
    (target_date) is within that many days and that aren't drafted yet -- so 'plan a year, generate
    just-in-time' works (each piece drafts ~a week before it publishes, not all at once)."""
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        wos = []
        # prefer tracked work orders (they carry status + db id). target_date/status/has_draft are
        # read so the JIT (due_within_days) mode can pick only near-due, not-yet-drafted pieces.
        try:
            rows = conn.execute(
                "SELECT id, wo_code, title, capability, execution, instruction, status, target_date, "
                "gap_specifics, "
                "COALESCE(superseded, false) AS superseded, "
                "EXISTS(SELECT 1 FROM content_drafts d WHERE d.work_order_id=work_orders.id) AS has_draft "
                "FROM work_orders WHERE business_id=%s", (business_id,)
            ).fetchall()
            for r in rows:
                # gap_specifics carries the piece's gap linkage (source_query = the weak AI query it
                # fixes) + the strategist's content_type + campaign role. Without it the plan/JIT path
                # degraded target_query, keyword scoping, grounding, and the per-type spec to the TITLE.
                gs = r.get("gap_specifics") if isinstance(r.get("gap_specifics"), dict) else {}
                wos.append({"_db_id": r["id"], "wo_code": r["wo_code"], "title": r["title"],
                            "capability": r["capability"], "execution": r["execution"],
                            "instruction": r["instruction"], "status": r.get("status"),
                            "target_date": r.get("target_date"), "superseded": r.get("superseded"),
                            "has_draft": r.get("has_draft"), "gap_specifics": gs,
                            "target_query": gs.get("source_query"),
                            "content_type": gs.get("content_type")})
        except Exception as e:  # noqa: BLE001
            # Don't silently fall through to plan-JSON work orders (which lack _db_id, so drafts
            # generate WITHOUT work-order linkage and approve() can't advance the WO) with no trace.
            log.warning("content_generator: tracked work-order query failed (%s) -- falling back to "
                        "plan JSON; generated drafts may not link to work orders.", e)
        if not wos:
            plan = conn.execute(
                "SELECT plan FROM strategy_plans WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                (business_id,),
            ).fetchone()
            if plan:
                p = plan["plan"] if isinstance(plan["plan"], dict) else json.loads(plan["plan"])
                wos = p.get("work_orders", [])
    biz = dict(biz)
    # Budget guard (rec 10b): drafting a batch is a multi-call LLM spend per work order (outline +
    # draft + eval + revisions + compliance). Refuse to start when the business is already at/over its
    # monthly cap, mirroring the audit + gap-model guards. The cap is the runaway backstop.
    if llm.cost.over_budget(business_id):
        raise SystemExit(
            f"Business {business_id} is at/over its monthly budget "
            f"(${llm.cost.month_spend(business_id):.2f} / ${llm.cost.budget_for(business_id):.2f}); "
            f"draft generation skipped. Raise monthly_budget_usd in business_config to proceed.")
    created = []
    eligible = 0   # WOs that are a generatable content type + auto/semi (i.e. we actually try them)
    budget_stopped = False
    for wo in wos:
        # An explicitly TARGETED work order (only_wo) is a direct 'generate this' click: honor it
        # regardless of JIT window or manual execution (this is how an opt-in per-campaign video plan
        # is produced on click). Batch/JIT runs still apply both filters below.
        targeted = bool(only_wo) and wo.get("_db_id") == only_wo
        if only_wo and not targeted:
            continue
        # JIT filter (due_within_days): draft ONLY near-due, not-yet-drafted, still-open pieces --
        # so the year's plan generates gradually into each drip slot, under the budget cap, instead
        # of drafting all 50+ pieces up front.
        if due_within_days is not None and not targeted:
            if wo.get("superseded") or wo.get("has_draft"):
                continue
            if (wo.get("status") or "pending") not in ("pending", "in_progress"):
                continue
            td = wo.get("target_date")
            if not td:
                continue
            import datetime as _dt
            _sd = td if isinstance(td, _dt.date) else _dt.date.fromisoformat(str(td)[:10])
            if _sd > _dt.date.today() + _dt.timedelta(days=due_within_days):
                continue
        # only auto/semi content WOs run in a BATCH; a targeted WO generates regardless of execution.
        if not targeted and (wo.get("execution") or "auto") not in ("auto", "semi"):
            continue
        if not _asset_type_for(wo):
            continue  # not a generatable content type (schema-only manual tasks, etc.)
        # Re-check the cap between work orders so a long batch STOPS the moment it crosses the
        # ceiling instead of draining the whole month's budget in one run.
        if llm.cost.over_budget(business_id):
            log.warning("Budget cap reached mid-batch for business %d after %d draft(s); stopping "
                        "generation (remaining work orders will be picked up next run).",
                        business_id, len(created))
            budget_stopped = True
            break
        eligible += 1
        # The explicit content_type (from Create Content) applies to the single targeted WO so its
        # asset_type/rich-type is resolved deterministically instead of guessed from the title.
        did = generate_for_wo(business_id, wo, biz,
                              content_type=(content_type if only_wo and wo.get("_db_id") == only_wo else None))
        if did:
            created.append(did)
    log.info("Generated %d draft(s) for business %d (%d eligible content WO(s))",
             len(created), business_id, eligible)
    # Silent-failure guard: eligible content WOs but ZERO drafts produced is a real failure
    # (orchestrator LLM unavailable/misconfigured, or every target already published) -- NOT a
    # success. Raise so the job is marked failed instead of a misleading "complete". A budget-driven
    # stop is NOT a failure (it's the cap doing its job), so it never trips this guard.
    if eligible and not created and not budget_stopped:
        raise RuntimeError(
            f"generate_drafts produced 0 drafts from {eligible} eligible content work order(s) for "
            f"business {business_id}: generation failed (check the orchestrator LLM key/availability) "
            f"or every target is already published. Not marking this run successful."
        )
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


def _publish_channels_for(asset_type: Optional[str], surface: Optional[str]) -> list[str]:
    """Map an approved asset to the publish channel(s) create_targets should attempt at approve
    time. Owned long-form (article / owned page on the own site) -> the WordPress blog; a GBP post
    -> gbp_post; a generic social post -> the connected social networks (create_targets skips any
    channel without a healthy connection, so listing several is safe -- unconnected ones are no-ops).
    An unrecognized type returns [] and the asset simply stays manual (paste-the-URL) as before."""
    at = (asset_type or "").strip().lower()
    if at in ("article", "owned_page", "own_page", "blog", "long_form", "landing_page", "page"):
        return ["wp_blog"]
    if at in ("gbp_post", "gbp", "google_business_post", "google_business"):
        return ["gbp_post"]
    if at.startswith("social"):
        return ["social_fb_page", "social_ig", "social_li_org", "social_x"]
    return []


def approve(draft_id: int, reviewer: str, override_reason: Optional[str] = None,
            publish_now: bool = False) -> None:
    """Approve a draft and promote it into the assets table (the only path to
    'published' state). Human action only.

    Cadence-aware publishing (Phase 3): if the linked work order has a FUTURE target_date (its
    drip slot on the content calendar), the publish target is SCHEDULED for that date rather than
    posted immediately -- so a year of approved content posts out gradually on its own. Pieces whose
    slot is now/past publish immediately (prior behavior), and publish_now=True forces immediate
    publishing regardless of the schedule. Purely a scheduling change; the drain does the posting.

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
        # Exact-content fingerprint on the asset (matches the draft's content_hash) so future
        # generation can detect a byte-identical duplicate of already-published content.
        body_hash = hashlib.sha256((d.get("body") or "").encode("utf-8")).hexdigest()
        # Copy the draft's compliance verdict onto the asset: the publish runner re-checks
        # assets.compliance_pass IS TRUE before any auto-post (Integrations Phase 2).
        # published_at is set EXPLICITLY (not left to the column DEFAULT) so an approved owned asset
        # reliably carries a produced-on timestamp the score/activity queries count -- the dashboard
        # "published this period" rollup, the freshness sweep, and traffic attribution all read it.
        # Structured data (Phase 5B): build the JSON-LD (Article/FAQPage/VideoObject/LocalBusiness)
        # for this asset and store it on the asset meta so the publish path injects a
        # <script type="application/ld+json"> into the page (Google structured-data guides).
        # Deterministic + fail-safe: a schema error must never block an approval.
        _meta = {"from_draft": draft_id}
        try:
            from . import content_schema as _cs
            from . import business_profile as _bp2
            import datetime as _dt2
            _bz = dict(conn.execute("SELECT name, domain, geo FROM businesses WHERE id=%s",
                                    (d["business_id"],)).fetchone() or {})
            try:
                _byline = (_bp2.for_business(d["business_id"]) or {}).get("byline_reviewer") or None
            except Exception:  # noqa: BLE001
                _byline = None
            _imgs = (d.get("quality_notes") or {}).get("images") if isinstance(d.get("quality_notes"), dict) else None
            _script = _cs.to_script(_cs.build_jsonld(
                d.get("asset_type") or "article", d.get("title") or "", d.get("body") or "", _bz,
                byline=_byline, published_at=_dt2.date.today().isoformat(), geo=(_bz.get("geo") or ""),
                images=_imgs))
            if _script:
                _meta["schema_jsonld"] = _script
        except Exception as e:  # noqa: BLE001 -- schema is best-effort; never block approve
            log.debug("approve: schema build skipped for draft %s: %s", draft_id, e)
        asset = conn.execute(
            """INSERT INTO assets (business_id, work_order_id, asset_type, title, surface, meta,
                                   summary, published_status, compliance_pass, body_hash, published_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s, now()) RETURNING id""",
            (d["business_id"], d["work_order_id"], d["asset_type"], d["title"],
             "own_site", json.dumps(_meta), summary, d.get("compliance_pass"), body_hash),
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
        # Immutable compliance sign-off record (FINRA 2210 / SEC recordkeeping). Reuses body_hash
        # computed above (same sha256 of the draft body).
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
    # Real publish path (Integrations Phase 2): best-effort enqueue of one publish target per channel
    # that HAS a healthy connection -- so "Approve" on a connected tenant actually queues the post,
    # not just mints a manual asset. Called AFTER commit so the asset row (the target's FK parent) is
    # visible to create_targets' own connection. Fail-safe by contract: create_targets does no network
    # I/O and skips unconnected channels, and any error here is swallowed so it can never fail approve
    # -- the asset is already durably approved. The drain (worker) does the actual posting later.
    try:
        channels = _publish_channels_for(d["asset_type"], "own_site")
        if channels:
            try:
                from .publishing import runner as _pub_runner
            except ImportError:  # pragma: no cover -- loose-script fallback
                from publishing import runner as _pub_runner  # type: ignore
            # Cadence-aware schedule: publish on the work order's target_date (its drip slot) when that
            # is in the future; otherwise (no WO / past-due / publish_now) post immediately. This is
            # what makes a year of approved content post out gradually instead of all at once.
            scheduled_for = None
            if not publish_now and d.get("work_order_id"):
                import datetime as _dt
                try:
                    with db() as _c2:
                        _wr = _c2.execute("SELECT target_date FROM work_orders WHERE id=%s",
                                          (d["work_order_id"],)).fetchone()
                    _td = _wr.get("target_date") if _wr else None
                    if _td:
                        _sd = _td if isinstance(_td, _dt.date) else _dt.date.fromisoformat(str(_td)[:10])
                        if _sd > _dt.date.today():
                            scheduled_for = _dt.datetime.combine(_sd, _dt.time(9, 0))
                except Exception as _e:  # noqa: BLE001 -- date lookup must never block approve
                    log.debug("approve: cadence date lookup skipped for wo %s: %s",
                              d.get("work_order_id"), _e)
            res = _pub_runner.create_targets(
                d["business_id"], asset["id"], channels, work_order_id=d["work_order_id"],
                scheduled_for=scheduled_for)
            if res.get("created"):
                log.info("approve: %s %d publish target(s) for asset %d (%s)",
                         ("scheduled" if scheduled_for else "queued"), len(res["created"]),
                         asset["id"], ", ".join(channels))
    except Exception as e:  # noqa: BLE001 -- publishing is best-effort; approve already committed
        log.warning("approve: create_targets skipped for asset %d: %s", asset["id"], e)


def reject(draft_id: int, reviewer: str, notes: Optional[str]) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE content_drafts SET status='rejected', reviewer=%s, reviewed_at=now(), "
            "quality_notes = quality_notes || %s::jsonb, updated_at=now() WHERE id=%s",
            (reviewer, json.dumps({"reject_notes": notes or ""}), draft_id),
        )
        conn.commit()
    log.info("Draft %d rejected by %s", draft_id, reviewer)


# ----------------------------------------------------------------------------
# Social atomization (Phase 5) -- turn one long-form piece into per-platform posts
# ----------------------------------------------------------------------------
# Per-platform format hints for atomization. The SET of platforms is profile-driven (social_channels),
# so a b2b_saas tenant gets LinkedIn+X, an ecommerce/beauty tenant gets Instagram/TikTok/Pinterest, etc.
_CHANNEL_HINTS = {
    "linkedin": "LinkedIn = professional, 1-2 short paragraphs + a takeaway",
    "x": "X = one punchy post under 280 characters",
    "twitter": "X = one punchy post under 280 characters",
    "facebook": "Facebook = warm + conversational, 2-3 sentences",
    "instagram": "Instagram = a hook-led caption with 3-5 relevant hashtags",
    "tiktok": "TikTok = a short hook-led caption / on-screen text idea with 3-5 hashtags",
    "pinterest": "Pinterest = a keyword-rich pin description with a clear value hook",
    "youtube": "YouTube = a Shorts caption / hook plus a one-line description",
    "threads": "Threads = a casual, conversational short post",
}
_DEFAULT_ATOMIZE_CHANNELS = ["linkedin", "x", "facebook", "instagram"]


def _atomize_system(channels: Optional[list] = None) -> str:
    """Build the atomization prompt for the tenant's actual social channels (profile.social_channels).
    Unknown channels are dropped; an empty/invalid set falls back to the generic 4-channel default."""
    chans = [c for c in (channels or _DEFAULT_ATOMIZE_CHANNELS) if c in _CHANNEL_HINTS]
    chans = list(dict.fromkeys(chans)) or list(_DEFAULT_ATOMIZE_CHANNELS)
    surfaces = ", ".join(chans)
    hint_lines = "; ".join(_CHANNEL_HINTS[c] for c in chans)
    atoms_shape = ",".join('{"surface":"%s","text":"..."}' % c for c in chans)
    return (
        "You are a social media strategist. Atomize the given long-form article into short, ready-to-post "
        f"social posts, ONE per platform: {surfaces}. GROUND every claim in the article -- NEVER add "
        "facts, statistics, offers, credentials, or claims not present in it. Match each platform: "
        f"{hint_lines}. Keep the business name/city where natural. Never fabricate. Return ONLY JSON: "
        '{"atoms":[' + atoms_shape + "]}"
    )


ATOMIZE_SYSTEM = _atomize_system()   # generic-default alias; per-tenant built in atomize_draft
_SURFACE_LABEL = {"linkedin": "LinkedIn", "x": "X/Twitter", "twitter": "X/Twitter",
                  "facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok",
                  "pinterest": "Pinterest", "youtube": "YouTube", "threads": "Threads",
                  "gbp": "Google Business Profile"}


def atomize_draft(business_id: int, draft_id: int, batch_id: Optional[int] = None) -> dict:
    """Derive human-gated social posts from a long-form draft (Phase-5 atomization): one grounded
    post per platform, stored as pending_review drafts (compliance UNscreened -> a principal must
    sign off to approve). NEVER auto-posts -- AUTOPOST_GLOBAL_ENABLED still governs any posting.
    batch_id links the posts into a content batch ATOMICALLY at insert (so a later grading failure
    can't orphan them from the batch)."""
    _ensure_table()
    with db() as conn:
        d = conn.execute("SELECT id, work_order_id, title, body, target_query FROM content_drafts "
                         "WHERE id=%s AND business_id=%s", (draft_id, business_id)).fetchone()
    if not d:
        return {"ok": False, "error": "draft not found"}
    body = (d.get("body") or "").strip()
    if len(body) < 120:
        return {"ok": False, "error": "draft is too short to atomize into social posts"}
    payload = json.dumps({"title": d.get("title") or "", "article": body[:6000]})
    # Atomize to the tenant's ACTUAL social channels (b2b_saas -> LinkedIn+X; ecommerce -> +TikTok/
    # Pinterest), not a fixed 4-channel set. Fail-safe -> the generic default channels.
    try:
        from . import business_profile as _bp
        _channels = _bp.for_business(business_id).get("social_channels") or _DEFAULT_ATOMIZE_CHANNELS
    except Exception:  # noqa: BLE001
        _channels = _DEFAULT_ATOMIZE_CHANNELS
    res = llm.orchestrator_json(_atomize_system(_channels), payload, tier="mid",
                                bill={"business_id": business_id, "operation": "atomize"}) or {}
    atoms = res.get("atoms") if isinstance(res, dict) else None
    if not isinstance(atoms, list) or not atoms:
        return {"ok": False, "error": "could not generate social posts (content LLM unavailable)"}
    created: list[int] = []
    with db() as conn:
        for a in atoms[:6]:
            if not isinstance(a, dict):
                continue
            surface = str(a.get("surface") or "social").lower().strip()
            text = (a.get("text") or "").strip()
            if not text:
                continue
            label = _SURFACE_LABEL.get(surface, surface.title() or "Social")
            row = conn.execute(
                """INSERT INTO content_drafts
                   (business_id, work_order_id, asset_type, title, body, target_query,
                    quality_score, quality_notes, revision_count, compliance_pass,
                    compliance_flags, status, highlighted_sections, placeholders_pending, content_hash,
                    batch_id, content_type)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'social_post') RETURNING id""",
                (business_id, d.get("work_order_id"), f"{surface}_post",
                 f"{d.get('title') or 'Post'} — {label}", text, d.get("target_query"),
                 None, json.dumps({"atomized_from": draft_id, "surface": surface}), 0, None,
                 json.dumps([]), "pending_review", json.dumps([]), json.dumps([]),
                 hashlib.sha256(text.encode("utf-8")).hexdigest(), batch_id)).fetchone()
            created.append(int(row["id"]))
        conn.commit()
    log.info("Atomized draft %d -> %d social posts", draft_id, len(created))
    return {"ok": True, "created": len(created), "draft_ids": created, "source_draft_id": draft_id}


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
        # Re-screen with the tenant's compliance pack: finance hard-rules only for a regulated-finance
        # tenant, universal-only otherwise (so a generic tenant's edit isn't failed on finance patterns).
        _reg_fin = False
        try:
            from . import business_profile as _bp
            _reg_fin = bool(_bp.for_business(d["business_id"]).get("regulated_financial"))
        except Exception:  # noqa: BLE001
            _reg_fin = False
        flags = _deterministic_compliance(new_body or "", regulated_financial=_reg_fin)
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
