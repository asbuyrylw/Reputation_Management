"""
Reputation Crowding-Out Engine -- draft quality analysis (Wave 2: on-page + citation-readiness + fact-check)
===========================================================================================================
Three scorers that grade a content draft so it actually RANKS and gets QUOTED by AI:

  * on_page_score   (item 6) -- structure (H1/H2), keyword placement, image+alt presence, internal
                                links, readability, schema suggestion. The "optimized for Google" check.
  * citation_ready  (item 7) -- "will an AI quote this?": a crisp answer to the target query up top,
                                a quotable stat, FAQ/Q&A structure, schema-worthy content.
  * fact_check      (item 10) -- extract factual claims + flag the ones not corroborated by the crawled
                                site (LLM; keyless-safe no-op). High-value for a regulated firm.

All deterministic except fact_check's optional LLM pass. Results are stored in
content_drafts.quality_notes (JSONB) and surfaced on the draft-review card; on_page issues also feed
the gap model's site_technical_gaps.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("content_quality")

# --- markdown/text parsing helpers ----------------------------------------------------------
_H1 = re.compile(r"^\s{0,3}#\s+\S", re.M)
_H2 = re.compile(r"^\s{0,3}##\s+\S", re.M)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+)$", re.M)
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")          # ![alt](url)
_LINK = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")   # [text](url)
_STAT = re.compile(r"(?:\$\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|b|million|billion))?)"   # leading currency: $50, $2.3M
                   r"|(?:\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|k\b|years?|clients?|"
                   r"customers?|reviews?|\$))", re.I)
_SENT = re.compile(r"[.!?]+\s")
_HEADING_LVL = re.compile(r"^(\s{0,3})(#{1,6})\s+(.+)$", re.M)
_FRESH = re.compile(r"(last[-\s]?updated|updated on|as of|reviewed on)\b", re.I)
_SYLL = re.compile(r"[aeiouy]+", re.I)
_PASSIVE = re.compile(r"\b(?:was|were|is|are|been|be|being)\s+\w+ed\b", re.I)


def _words(body: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", body or "")


def _terms(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (q or "").lower()) if len(t) > 2]


def _avg_sentence_len(body: str) -> float:
    text = re.sub(r"[#*_>`\-]", " ", body or "")
    sents = [s for s in _SENT.split(text) if s.strip()]
    if not sents:
        return 0.0
    return round(sum(len(_words(s)) for s in sents) / len(sents), 1)


# ============================================================================================
# Item 6 -- on-page SEO score
# ============================================================================================
def on_page_score(body: str, target_query: str = "", keywords: Optional[list[str]] = None) -> dict:
    body = body or ""
    wc = len(_words(body))
    h1 = len(_H1.findall(body))
    h2 = len(_H2.findall(body))
    imgs = _IMG.findall(body)
    imgs_with_alt = sum(1 for alt, _ in imgs if alt.strip())
    links = _LINK.findall(body)
    first_chunk = " ".join(_words(body)[:120]).lower()
    qterms = _terms(target_query)
    q_in_intro = bool(qterms) and sum(t in first_chunk for t in qterms) >= max(1, len(qterms) // 2)
    headings = [h.lower() for h in _HEADING.findall(body)]
    q_in_heading = bool(qterms) and any(any(t in h for t in qterms) for h in headings)
    avg_sent = _avg_sentence_len(body)
    kw = [k.lower() for k in (keywords or [])]
    body_low = body.lower()
    kw_present = sum(1 for k in kw if k in body_low)

    checks = []  # (passed, weight, label, fix)
    checks.append((h1 == 1, 15, "Exactly one H1 title",
                   "Add a single top-level H1 heading." if h1 == 0 else "Use only one H1; demote the rest to H2."))
    checks.append((h2 >= 2, 12, "At least 2 H2 sections", "Break the content into 2+ H2 sections so AI can extract sub-answers."))
    checks.append((wc >= 300, 12, "300+ words", f"Only {wc} words — thin content ranks poorly; expand to 300+."))
    checks.append((q_in_intro, 14, "Target query answered in the intro", "Answer the target search in the first paragraph."))
    checks.append((q_in_heading, 10, "Target query in a heading", "Put the target search (or a close variant) in a heading."))
    checks.append((len(imgs) >= 1, 8, "Has at least one image", "Add a relevant image (diagram, photo, or quote card)."))
    checks.append((len(imgs) == 0 or imgs_with_alt == len(imgs), 10, "All images have alt text",
                   "Every image needs descriptive alt text (accessibility + image SEO)."))
    checks.append((len(links) >= 1, 9, "Has internal/outbound links", "Link to a relevant owned page and one authoritative source."))
    checks.append((10 <= avg_sent <= 24, 10, "Readable sentence length", f"Avg sentence is {avg_sent} words — aim for 10–24."))
    if kw:
        checks.append((kw_present >= max(1, len(kw) // 3), 0, "Target keywords present", "Weave in more target keywords naturally."))

    earned = sum(w for ok, w, _, _ in checks if ok)
    possible = sum(w for _, w, _, _ in checks)
    score = round(100 * earned / possible) if possible else 0
    issues = [{"label": label, "fix": fix} for ok, w, label, fix in checks if not ok]
    # schema suggestion based on content shape
    schema = "FAQPage" if any(h.strip().endswith("?") for h in headings) else "Article"
    return {"score": score, "word_count": wc, "h1": h1, "h2": h2, "images": len(imgs),
            "images_with_alt": imgs_with_alt, "links": len(links), "avg_sentence_len": avg_sent,
            "suggested_schema": schema, "issues": issues}


# ============================================================================================
# Item 7 -- citation-readiness ("will an AI quote this?")
# ============================================================================================
def citation_ready(body: str, target_query: str = "") -> dict:
    body = body or ""
    headings = [h for h in _HEADING.findall(body)]
    first_para = (re.split(r"\n\s*\n", body.strip(), 1)[0] if body.strip() else "")
    qterms = _terms(target_query)
    crisp_answer = bool(qterms) and sum(t in first_para.lower() for t in qterms) >= max(1, len(qterms) // 2) \
        and len(_words(first_para)) >= 15
    has_stat = bool(_STAT.search(body))
    faq = sum(1 for h in headings if h.strip().endswith("?"))
    has_qa = faq >= 1
    listy = bool(re.search(r"^\s*[-*]\s+\S", body, re.M)) or bool(re.search(r"^\s*\d+\.\s+\S", body, re.M))

    checks = [
        (crisp_answer, 35, "Answers the question up top", "Lead with a 2–3 sentence direct answer to the target query."),
        (has_stat, 25, "Has a quotable stat/number", "Add a concrete number or stat AI can lift (e.g. '4.9★ from 120 reviews')."),
        (has_qa, 20, "Uses a Q&A / FAQ structure", "Add question-form headings — AI quotes Q&A blocks readily."),
        (listy, 20, "Has a scannable list", "Add a bulleted or numbered list of the key points."),
    ]
    earned = sum(w for ok, w, _, _ in checks if ok)
    score = earned  # weights sum to 100
    tips = [{"label": label, "fix": fix} for ok, w, label, fix in checks if not ok]
    return {"score": score, "faq_headings": faq, "tips": tips}


# ============================================================================================
# Item 10 -- fact-claim verification (LLM; keyless-safe)
# ============================================================================================
_FACTCHECK_SYSTEM = (
    "You verify a DRAFT marketing/info page against the business's KNOWN FACTS (from its crawled "
    "site + audit). Extract each concrete, checkable factual claim in the draft (names, numbers, "
    "credentials, awards, years, affiliations, guarantees). For each, decide if the KNOWN FACTS "
    "support it. Return STRICT JSON: {claims: [{claim: str, status: 'supported'|'unverifiable'|"
    "'contradicted', note: str}]}. Be strict: a claim with no support in the known facts is "
    "'unverifiable' (it may still be true, but must be confirmed before publishing). JSON only."
)


def fact_check(body: str, site_summary: Optional[dict] = None) -> dict:
    """Extract + verify factual claims against the crawled site facts. Keyless-safe: returns
    {skipped} without an LLM. The caller surfaces 'unverifiable'/'contradicted' before approval."""
    if not (body or "").strip():
        return {"claims": [], "unverified": 0}
    # The orchestrator LLM lives in ai_state_audit (imported as `llm` across the engine). The old
    # `from . import llm` referenced a module that doesn't exist -> ModuleNotFoundError, which (via
    # analyze_draft's single-return) silently discarded EVERY grade on every generated draft.
    try:
        from . import ai_state_audit as llm
    except ImportError:  # pragma: no cover
        import ai_state_audit as llm  # type: ignore
    import json as _json
    payload = _json.dumps({"draft": body[:6000], "known_facts": site_summary or {}}, default=str)
    res = llm.orchestrator_json(_FACTCHECK_SYSTEM, payload, tier="cheap")
    if not res or not isinstance(res, dict):
        return {"skipped": True, "claims": [], "unverified": 0}
    claims = res.get("claims") or []
    unverified = sum(1 for c in claims if c.get("status") in ("unverifiable", "contradicted"))
    return {"claims": claims[:25], "unverified": unverified}


# ============================================================================================
# Structure / layout grade (Phase 1, Rec 2) -- heading hierarchy + organization, 0-100
# ============================================================================================
def _heading_map(body: str) -> list[dict]:
    return [{"level": len(m.group(2)), "text": m.group(3).strip()} for m in _HEADING_LVL.finditer(body or "")]


def structure_score(body: str) -> dict:
    """Grade heading hierarchy + layout for AI extraction (a dedicated layout score, not just booleans)."""
    body = body or ""
    hmap = _heading_map(body)
    h1 = sum(1 for h in hmap if h["level"] == 1)
    h2 = sum(1 for h in hmap if h["level"] == 2)
    # hierarchy: never jump more than one level deeper than the previous heading (no H3 before an H2)
    hierarchy_valid, prev = True, 0
    for h in hmap:
        if prev and h["level"] > prev + 1:
            hierarchy_valid = False
            break
        prev = h["level"]
    # section balance: no section runs far longer than the average
    sections = re.split(r"^\s{0,3}#{1,6}\s+.+$", body, flags=re.M)
    seclens = [n for n in (len(_words(s)) for s in sections) if n > 0]
    avgsec = (sum(seclens) / len(seclens)) if seclens else 0
    balanced = (not seclens) or max(seclens) <= max(160, 5 * avgsec)
    imgs = _IMG.findall(body)
    has_lists = bool(re.search(r"^\s*[-*]\s+\S", body, re.M)) or bool(re.search(r"^\s*\d+\.\s+\S", body, re.M))
    avg_sent = _avg_sentence_len(body)
    checks = [
        (h1 == 1, 20, "Single H1 title", "Use exactly one H1." if h1 == 0 else "Only one H1; demote the rest."),
        (h2 >= 2, 20, "2+ H2 sections", "Break the body into 2+ H2 sections."),
        (hierarchy_valid, 15, "Valid heading hierarchy", "Don't skip heading levels (e.g. an H3 before any H2)."),
        (balanced, 15, "Balanced section lengths", "One section is far longer than the rest — split it."),
        (len(imgs) >= 1, 10, "Image present", "Add a relevant image near the top."),
        (has_lists, 10, "Scannable list block", "Add a bulleted or numbered list of key points."),
        (10 <= avg_sent <= 24, 10, "Readable sentence length", f"Avg sentence {avg_sent} words — aim 10–24."),
    ]
    earned = sum(w for ok, w, _, _ in checks if ok)
    possible = sum(w for _, w, _, _ in checks)
    return {"score": round(100 * earned / possible) if possible else 0,
            "hierarchy_valid": hierarchy_valid,
            "structure_map": [{"level": h["level"], "text": h["text"][:80]} for h in hmap[:24]],
            "issues": [{"label": l, "fix": f} for ok, w, l, f in checks if not ok]}


# ============================================================================================
# Keyword density (Phase 1, Rec 6) -- occurrence rate per keyword, flag under/over-optimized
# ============================================================================================
def keyword_density_check(body: str, keywords: Optional[list[str]] = None) -> dict:
    words = _words(body)
    wc = len(words) or 1
    low = " ".join(words).lower()
    out, issues = [], []
    for k in (keywords or [])[:20]:
        kl = (k or "").lower().strip()
        if not kl:
            continue
        occ = low.count(kl)
        density = round(100 * occ * len(kl.split()) / wc, 2)
        band = "missing" if occ == 0 else "low" if density < 0.3 else "high" if density > 2.0 else "ok"
        out.append({"keyword": k, "count": occ, "density_pct": density, "band": band})
        if band == "missing":
            issues.append({"label": f"Missing keyword: “{k}”", "fix": f"Weave “{k}” in naturally."})
        elif band == "high":
            issues.append({"label": f"Over-optimized: “{k}” at {density}%", "fix": f"Ease off “{k}” — above ~2% reads as stuffing."})
    return {"keyword_densities": out, "issues": issues}


# ============================================================================================
# Readability grade (Phase 1, EXTRA #10) -- Flesch-Kincaid grade + passive voice
# ============================================================================================
def _syllables(word: str) -> int:
    return max(1, len(_SYLL.findall(word.lower().rstrip("e"))))


def readability_score(body: str) -> dict:
    text = re.sub(r"[#*_>`\[\]()!]", " ", body or "")
    words = _words(text)
    sents = [s for s in _SENT.split(text) if s.strip()]
    nw, ns = len(words), max(1, len(sents))
    if nw == 0:
        return {"grade": None, "avg_sentence_len": 0, "passive_hits": 0, "issues": []}
    syl = sum(_syllables(w) for w in words)
    grade = round(0.39 * (nw / ns) + 11.8 * (syl / nw) - 15.59, 1)
    passive = len(_PASSIVE.findall(text))
    issues = []
    if grade > 12:
        issues.append({"label": f"Reading grade {grade} (hard)", "fix": "Shorten sentences + simpler words; aim grade 8–10."})
    if passive > max(3, ns // 4):
        issues.append({"label": f"{passive} passive-voice phrases", "fix": "Rewrite passive sentences in active voice."})
    return {"grade": grade, "avg_sentence_len": round(nw / ns, 1), "passive_hits": passive,
            "target": "grade 8–10 for a broad audience", "issues": issues}


# ============================================================================================
# NeuronWriter-style term coverage (Phase 1, Rec 1 backend) -- covered vs missing SERP terms
# ============================================================================================
def term_coverage(body: str, terms: Optional[list[str]] = None) -> dict:
    low = (body or "").lower()
    terms = [t for t in (terms or []) if t and str(t).strip()]
    covered = [t for t in terms if str(t).lower() in low]
    missing = [t for t in terms if str(t).lower() not in low]
    n = len(terms)
    return {"terms_total": n, "terms_covered": covered[:60], "terms_missing": missing[:60],
            "covered_pct": round(100 * len(covered) / n) if n else None}


# ============================================================================================
# AEO sub-scores (Phase 1, Rec 7) -- per-pillar "will an AI quote this?" incl entity + freshness
# ============================================================================================
def aeo_score(body: str, target_query: str = "", business_name: str = "", geo: str = "") -> dict:
    body = body or ""
    headings = _HEADING.findall(body)
    first_para = (re.split(r"\n\s*\n", body.strip(), 1)[0] if body.strip() else "")
    qterms = _terms(target_query)
    crisp = bool(qterms) and sum(t in first_para.lower() for t in qterms) >= max(1, len(qterms) // 2) \
        and 15 <= len(_words(first_para)) <= 90
    has_stat = bool(_STAT.search(body))
    faq = sum(1 for h in headings if h.strip().endswith("?"))
    low = body.lower()
    name_hits = low.count((business_name or "").lower()) if (business_name or "").strip() else 0
    entity_clear = ((not (business_name or "").strip()) or name_hits >= 3) and \
                   ((not (geo or "").strip()) or (geo or "").lower() in low)
    fresh = bool(_FRESH.search(body))
    pillars = [
        {"name": "Direct answer up top", "ok": crisp, "weight": 25, "fix": "Open with a crisp 40–60 word answer to the target query."},
        {"name": "Quotable statistic", "ok": has_stat, "weight": 15, "fix": "Add a concrete, attributable number AI can lift."},
        {"name": "Q&A / FAQ structure", "ok": faq >= 1, "weight": 20, "fix": "Add question-form headings AI can quote."},
        {"name": "Entity clarity (name + place)", "ok": entity_clear, "weight": 20, "fix": "Name the business + city explicitly and consistently (3+ times)."},
        {"name": "Freshness marker", "ok": fresh, "weight": 10, "fix": "Add a visible ‘Last updated: <month year>’ line."},
        {"name": "Schema-ready shape", "ok": True, "weight": 10, "fix": ""},
    ]
    return {"score": sum(p["weight"] for p in pillars if p["ok"]),
            "suggested_schema": "FAQPage" if faq else "Article",
            "pillars": [{"name": p["name"], "score": p["weight"] if p["ok"] else 0, "max": p["weight"], "ok": p["ok"]} for p in pillars],
            "tips": [{"label": p["name"], "fix": p["fix"]} for p in pillars if not p["ok"]]}


# ============================================================================================
# GEO score -- Generative-Engine-Optimization citability grade, weighted PER CONTENT TYPE.
# Grounded in the Princeton GEO study + AEO guides: what makes AI assistants (ChatGPT/Perplexity/
# Gemini/AI Overviews) surface + CITE a page. Keyword stuffing does NOT help; answer-first blocks,
# quotable stats, inline citations to authoritative sources, question headings, schema, entity
# clarity, freshness, and extractable chunks DO. A single generic grade is wrong, so the weighting
# branches by content type (blog vs white paper vs landing vs local vs social).
# ============================================================================================
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_TABLE = re.compile(r"(^\s*\|.+\|\s*$)|(<table)", re.M | re.I)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+\S", re.M)
_EXT_LINK = re.compile(r"\]\((https?://[^)]+)\)")
_AUTH = re.compile(r"https?://[^)\s]*\.(gov|edu|org|ac\.[a-z]{2})\b", re.I)
_COMPARE = re.compile(r"\b(vs\.?|versus|compare(d)?|best|top \d|pros? and cons?|alternative)\b", re.I)
_REVIEW = re.compile(r"\b(review|rating|stars?|testimonial|\d(\.\d)?\s?/\s?5)\b", re.I)

# Per-content-type weight profiles (each sums to 100). Keys must exist in _geo_signal_score() below.
_GEO_PROFILES: dict[str, dict[str, int]] = {
    "blog":        {"answer_first": 18, "question_headings": 14, "stat_density": 14, "citation_density": 16, "schema": 8, "entity": 12, "freshness": 8, "chunkability": 10},
    "article":     {"answer_first": 18, "question_headings": 14, "stat_density": 14, "citation_density": 16, "schema": 8, "entity": 12, "freshness": 8, "chunkability": 10},
    "faq":         {"answer_first": 20, "question_headings": 22, "stat_density": 10, "citation_density": 12, "schema": 12, "entity": 12, "freshness": 4, "chunkability": 8},
    "white_paper": {"answer_first": 12, "stat_density": 20, "citation_density": 24, "entity": 12, "chunkability": 12, "schema": 8, "freshness": 6, "question_headings": 6},
    "landing_page":{"answer_first": 20, "comparison": 16, "entity": 16, "schema": 10, "question_headings": 12, "citation_density": 10, "freshness": 6, "chunkability": 10},
    "local_page":  {"nap": 22, "entity": 18, "answer_first": 16, "schema": 12, "reviews": 10, "freshness": 8, "question_headings": 8, "citation_density": 6},
}
# Social posts are a DISTRIBUTION/authority signal, not a citable document -- graded on their own
# lightweight rubric (see _geo_social), never the citability rubric.
_SOCIAL_TYPES = {"social_post", "social", "gbp_post", "linkedin_post", "x_post", "facebook_post", "instagram_post", "pinterest_post"}


def _geo_type_for(content_type: str, asset_type: str = "") -> str:
    ct = (content_type or asset_type or "article").strip().lower()
    if ct in _SOCIAL_TYPES or ct.endswith("_post"):
        return "social"
    aliases = {"owned_page": "landing_page", "page": "landing_page", "landing": "landing_page",
               "local": "local_page", "gbp": "local_page", "whitepaper": "white_paper",
               "white-paper": "white_paper", "guide": "article", "blog_post": "blog"}
    ct = aliases.get(ct, ct)
    return ct if ct in _GEO_PROFILES else "article"


def _geo_signal_score(body: str, target_query: str, business_name: str, geo: str) -> dict:
    """Compute each citability signal as a 0..1 strength (not just boolean) so the grade is graded."""
    body = body or ""
    words = _words(body)
    wc = max(1, len(words))
    headings = _HEADING.findall(body)
    first_para = (re.split(r"\n\s*\n", body.strip(), 1)[0] if body.strip() else "")
    qterms = _terms(target_query)
    low = body.lower()
    # answer-first: crisp, query-relevant opener of the right length
    answer_first = 1.0 if (bool(qterms) and sum(t in first_para.lower() for t in qterms) >= max(1, len(qterms)//2)
                           and 15 <= len(_words(first_para)) <= 90) else (0.4 if 12 <= len(_words(first_para)) <= 110 else 0.0)
    # question headings: ratio of headings that are questions (target ~30%+)
    qh = sum(1 for h in headings if h.strip().endswith("?"))
    question_headings = min(1.0, qh / max(1, round(len(headings) * 0.3))) if headings else 0.0
    # stat density: ~1 quotable stat per 200 words
    stats = len(_STAT.findall(body))
    stat_density = min(1.0, stats / max(1, wc / 200))
    # citation density: external links per ~300 words, authoritative sources bonus
    ext = _EXT_LINK.findall(body)
    auth = len(_AUTH.findall(body))
    cit = min(1.0, len(ext) / max(1, wc / 300))
    citation_density = min(1.0, cit + (0.25 if auth else 0))
    # schema-ready shape (question headings -> FAQ; else structured Article)
    schema = 1.0 if qh >= 1 else 0.6
    # entity clarity: business name (3+) + geo present
    name_hits = low.count((business_name or "").lower()) if (business_name or "").strip() else 0
    entity = 1.0 if (((not (business_name or "").strip()) or name_hits >= 3)
                     and ((not (geo or "").strip()) or (geo or "").lower() in low)) else (0.5 if name_hits >= 1 else 0.0)
    # freshness marker
    freshness = 1.0 if _FRESH.search(body) else 0.0
    # extractable chunks: reasonable section length + bullets/tables present
    sections = re.split(r"^\s{0,3}#{1,6}\s+.+$", body, flags=re.M)
    seclens = [len(_words(s)) for s in sections if _words(s)]
    avg_sec = sum(seclens) / len(seclens) if seclens else wc
    chunkability = (0.6 if avg_sec <= 300 else 0.3 if avg_sec <= 450 else 0.0) + (0.4 if (_BULLET.search(body) or _TABLE.search(body)) else 0.0)
    chunkability = min(1.0, chunkability)
    # local: NAP + reviews + comparison (commercial)
    nap = min(1.0, (0.5 if _PHONE.search(body) else 0) + (0.5 if ((geo or "").lower() in low and (business_name or "").lower() in low) else 0))
    reviews = 1.0 if _REVIEW.search(body) else 0.0
    comparison = 1.0 if (_COMPARE.search(body) and (_TABLE.search(body) or _BULLET.search(body))) else (0.4 if _COMPARE.search(body) else 0.0)
    return {"answer_first": answer_first, "question_headings": question_headings, "stat_density": stat_density,
            "citation_density": citation_density, "schema": schema, "entity": entity, "freshness": freshness,
            "chunkability": chunkability, "nap": nap, "reviews": reviews, "comparison": comparison,
            "_suggested_schema": ("LocalBusiness" if nap >= 0.5 else "FAQPage" if qh else "Article")}


_GEO_FIX = {
    "answer_first": "Open the page (and each section) with a self-contained 40–60 word answer an AI can lift.",
    "question_headings": "Phrase H2/H3s as the real questions people ask (they map to AI prompts).",
    "stat_density": "Add a concrete, attributable statistic roughly every 150–200 words.",
    "citation_density": "Cite authoritative primary sources inline (.gov/.edu/official) — the single biggest citation lever.",
    "schema": "Mark up as FAQPage/Article (LocalBusiness for a location page).",
    "entity": "Name the business + city explicitly and consistently; define who you are on first use.",
    "freshness": "Add a visible ‘Last updated: <month year>’ line — AI citations skew fresh.",
    "chunkability": "One idea per 200–400 word section; add bullets/tables so a passage lifts cleanly.",
    "nap": "State the business name, full address, and phone (NAP) so AI can triangulate the entity.",
    "reviews": "Reference ratings/reviews — a major local citation source.",
    "comparison": "Add a comparison table or ‘best/vs’ framing AI can quote for commercial queries.",
}


def _geo_social(body: str) -> dict:
    """Social posts: a distribution/authority signal, not a citable doc. Grade hook + length + link/CTA."""
    body = (body or "").strip()
    chars = len(body)
    checks = [
        ("Hook in the first line", bool(body) and len(body.split("\n", 1)[0]) <= 120, 30, "Lead with a punchy first line."),
        ("Length in platform range", 40 <= chars <= 2800, 25, "Keep it platform-appropriate (not empty, not a wall of text)."),
        ("Link / CTA back to owned page", bool(_EXT_LINK.search(body) or re.search(r"https?://|\b(learn more|read|link in bio|dm|contact)\b", body, re.I)), 30, "Link back to the owned page this amplifies."),
        ("Discoverability (hashtag/@)", bool(re.search(r"[#@]\w+", body)), 15, "Add a hashtag or handle for reach."),
    ]
    score = sum(pts for _, ok, pts, _ in checks if ok)
    return {"score": score, "content_type": "social", "profile": "social", "band": _band(score),
            "checks": [{"label": l, "ok": ok, "points": pts if ok else 0, "max": pts, "fix": (fix if not ok else "")} for l, ok, pts, fix in checks],
            "suggested_schema": None, "note": "Social is a distribution/authority signal — it widens the trust footprint AI uses to decide whom to cite, not a page AI cites directly."}


def _band(score) -> str:
    if score is None:
        return "n/a"
    return "strong" if score >= 75 else "solid" if score >= 55 else "weak"


def geo_score(body: str, target_query: str = "", content_type: str = "", asset_type: str = "",
              business_name: str = "", geo: str = "") -> dict:
    """0–100 GEO/citability grade, weighted for the content type. Social posts use their own rubric."""
    prof_key = _geo_type_for(content_type, asset_type)
    if prof_key == "social":
        return _geo_social(body)
    weights = _GEO_PROFILES[prof_key]
    sig = _geo_signal_score(body, target_query, business_name, geo)
    checks, earned = [], 0.0
    for name, w in weights.items():
        strength = float(sig.get(name, 0.0))
        pts = strength * w
        earned += pts
        checks.append({"label": name.replace("_", " ").title(), "ok": strength >= 0.75,
                       "points": round(pts, 1), "max": w, "fix": (_GEO_FIX.get(name, "") if strength < 0.75 else "")})
    score = round(earned)
    return {"score": score, "content_type": prof_key, "profile": prof_key, "band": _band(score),
            "suggested_schema": sig["_suggested_schema"],
            "checks": sorted(checks, key=lambda c: c["max"] - c["points"], reverse=True)}


# ============================================================================================
# SERP-competitor grade (Phase 3) -- benchmark the draft against the pages actually ranking.
# ============================================================================================
def serp_grade(body: str, benchmark: Optional[dict], keywords: Optional[list[str]] = None) -> dict:
    """Grade the draft vs. a serp_benchmark(): shared-term coverage + word-count-in-range, so the
    score means 'competitive with the ranking pages' rather than an absolute. {skipped} passthrough
    keeps it dormant-safe when Serper isn't configured."""
    if not benchmark or benchmark.get("skipped"):
        return {"skipped": True, "reason": (benchmark or {}).get("reason", "no SERP benchmark")}
    terms = benchmark.get("terms") or []
    low = (body or "").lower()
    covered = [t for t in terms if str(t).lower() in low]
    missing = [t for t in terms if str(t).lower() not in low]
    covered_pct = round(100 * len(covered) / len(terms)) if terms else None
    our_words = len(_words(body))
    target = benchmark.get("avg_word_count")
    # "in range" = within 25% under the ranking pages' average (over is fine)
    in_range = (target is None) or (our_words >= target * 0.75)
    # score: term coverage is the dominant signal (85%) plus a 15% credit for being in the ranking
    # pages' word-count range, so a well-scoped draft that covers the topic isn't scored purely on
    # verbatim term echo.
    score = None
    if covered_pct is not None:
        score = round(0.85 * covered_pct + (15 if in_range else 0))
    return {"score": score, "covered_pct": covered_pct,
            "terms_covered": covered[:60], "terms_missing": missing[:60],
            "our_words": our_words, "target_words": target, "in_range": in_range,
            "competitors": [{"title": c.get("title"), "link": c.get("link"), "words": c.get("words")}
                            for c in (benchmark.get("competitors") or [])[:10]],
            "questions": benchmark.get("questions") or []}


# ============================================================================================
# Search-intent + SERP-shape (Phase 1, EXTRA #3) -- tells the writer WHAT SHAPE to write
# ============================================================================================
def intent_and_serp(target_query: str = "", intent: str = "") -> dict:
    q = (target_query or "").lower()
    it = (intent or "").lower().strip()
    if not it:
        if re.search(r"\b(near me|in [a-z]+ (oh|ohio|[a-z]{2})|local)\b", q):
            it = "local"
        elif re.search(r"\b(buy|price|cost|hire|book|quote|best|top|vs|review)\b", q):
            it = "commercial"
        elif re.search(r"\b(how|what|why|when|guide|tips|ideas|examples)\b", q):
            it = "informational"
        else:
            it = "informational"
    shape = {
        "informational": "Answer-first + FAQ; target the featured snippet & People-Also-Ask.",
        "commercial": "Comparison / list format with a clear recommendation + pros & cons.",
        "transactional": "Concise, CTA-forward, with pricing / next-step clarity.",
        "local": "Local landing shape: NAP, service + city in the H1/intro, GBP/map.",
        "navigational": "Direct brand answer; keep it short.",
    }.get(it, "Answer-first + FAQ.")
    return {"intent": it, "recommended_shape": shape}


# ============================================================================================
# combined
# ============================================================================================
def analyze_draft(body: str, *, target_query: str = "", keywords: Optional[list[str]] = None,
                  site_summary: Optional[dict] = None, with_fact_check: bool = True,
                  neuron_terms: Optional[list[str]] = None, business_name: str = "",
                  geo: str = "", keyword_intent: str = "", content_type: str = "",
                  asset_type: str = "", serp_benchmark: Optional[dict] = None) -> dict:
    """Run every scorer -> a dict suitable for content_drafts.quality_notes. All deterministic +
    keyless except the optional fact_check LLM pass; new callers can pass neuron_terms / business_name
    / geo / keyword_intent for the richer term-coverage, entity, and intent grades."""
    # Per-scorer isolation: ONE scorer failing (esp. the LLM fact_check) must never discard the other
    # deterministic grades. Previously analyze_draft built + returned a single dict, so a fact_check
    # ImportError wiped on_page/citation_ready/aeo/structure/readability from EVERY draft's quality_notes.
    def _safe(name, fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 -- a failed scorer degrades to {skipped}, never sinks the grade
            log.warning("content grade scorer %s failed: %s", name, e)
            return {"skipped": True, "error": str(e)[:200]}

    out = {
        "on_page": _safe("on_page", lambda: on_page_score(body, target_query, keywords)),
        "citation_ready": _safe("citation_ready", lambda: citation_ready(body, target_query)),
        "structure": _safe("structure", lambda: structure_score(body)),
        "keyword_density": _safe("keyword_density", lambda: keyword_density_check(body, keywords)),
        "readability": _safe("readability", lambda: readability_score(body)),
        "aeo": _safe("aeo", lambda: aeo_score(body, target_query, business_name, geo)),
        "geo": _safe("geo", lambda: geo_score(body, target_query, content_type, asset_type, business_name, geo)),
        "intent_serp": _safe("intent_serp", lambda: intent_and_serp(target_query, keyword_intent)),
    }
    if neuron_terms:
        out["term_coverage"] = _safe("term_coverage", lambda: term_coverage(body, neuron_terms))
    # SERP-competitor benchmark (Phase 3): covered/missing terms + competitor table + a benchmarked
    # target ("beat the ranking pages"). Passed in by the caller (keyless/dormant-safe upstream).
    if serp_benchmark is not None:
        out["serp"] = _safe("serp", lambda: serp_grade(body, serp_benchmark, keywords))
    if with_fact_check:
        out["fact_check"] = _safe("fact_check", lambda: fact_check(body, site_summary))
    return out
