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


def _first_answer_para(body: str) -> str:
    """The first PROSE paragraph -- what 'answer-first' actually measures. Skips a leading H1/heading,
    a 'Last updated' freshness line, a hero image, and a short emphasis/quote meta line, so the check
    reads the real opening ANSWER (which conventionally sits right after the H1), not the title."""
    for b in re.split(r"\n\s*\n", (body or "").strip()):
        s = b.strip()
        if not s or s.startswith("#") or s.startswith("!["):
            continue
        if re.match(r"^[*_\s]*last\s+(updated|reviewed)\b", s, re.I):
            continue
        if s[0] in "*_>" and len(_words(s)) < 12:      # short emphasis/quote meta line
            continue
        return s
    blocks = [b.strip() for b in re.split(r"\n\s*\n", (body or "").strip()) if b.strip()]
    return blocks[0] if blocks else ""


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
    first_para = _first_answer_para(body)
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


def fact_check(body: str, site_summary: Optional[dict] = None, business_id: int | None = None) -> dict:
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
    res = llm.orchestrator_json(_FACTCHECK_SYSTEM, payload, tier="cheap",
                                bill={"business_id": business_id, "operation": "fact_check"})
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
    avg_sent = nw / ns
    issues = []
    if grade > 11:
        issues.append({"label": f"Reading grade {grade} (hard)", "fix": "Shorten sentences + simpler words; aim grade 6–8 (10–12 only for authoritative white papers)."})
    if avg_sent > 22:
        issues.append({"label": f"Avg sentence {round(avg_sent,1)} words (long)", "fix": "Aim 15–20 words/sentence; split long sentences (NN/g: concise copy tested +58% usability)."})
    if passive > max(3, ns // 4):
        issues.append({"label": f"{passive} passive-voice phrases", "fix": "Rewrite passive sentences in active voice."})
    return {"grade": grade, "avg_sentence_len": round(nw / ns, 1), "passive_hits": passive,
            "target": "grade 6–8 for a broad audience (NN/g)", "issues": issues}


# ============================================================================================
# Anti-slop / distinctiveness -- the machine-measurable "generic AI writing" tells research flags
# (formulaic openers/closers, non-committal hedges, filler transitions, buzzword vocabulary). These
# are what make automated content read as generic; we detect them so the grader penalizes them and
# the generator's revision loop can strip them. Kept SEPARATE from compliance (which bans regulated
# claims like guarantees/superlatives), and from the true-fact vocabulary (a piece may legitimately
# say "insurance" or "financial") -- this list is only the empty-calorie AI-tell phrases.
# ============================================================================================
_SLOP_PHRASES = [
    # formulaic openers / closers (whole-phrase, safe to flag)
    r"in today'?s (?:fast[- ]paced|digital|modern|ever[- ]changing|competitive) (?:world|age|era|landscape|environment)",
    r"in today'?s world", r"in the world of", r"in the realm of", r"in the fast[- ]paced world",
    r"in conclusion", r"in summary", r"to sum up", r"at the end of the day", r"when it comes to",
    r"last but not least", r"needless to say", r"as we all know", r"it goes without saying",
    # non-committal hedges
    r"it'?s (?:important|worth|crucial|essential) to (?:note|remember|mention|understand) that",
    r"it should be noted that", r"it is worth noting", r"generally speaking", r"that being said",
    # filler transitions
    r"furthermore", r"moreover", r"here'?s the kicker", r"rest assured", r"look no further",
    # buzzword / AI-tell vocabulary
    r"delve", r"delving", r"leverage", r"leveraging", r"foster", r"fostering", r"seamless(?:ly)?",
    r"tapestry", r"testament to", r"transformative", r"game[- ]chang", r"plethora", r"myriad",
    r"unlock(?:ing)?(?: the)? (?:potential|power|secret)", r"elevate", r"empower(?:ing)?",
    r"ever[- ]evolving", r"vibrant", r"bustling", r"dive into", r"deep dive", r"navigate the",
    r"cutting[- ]edge", r"unparalleled", r"in this (?:article|post|guide|blog)", r"we'?ll explore",
]
_SLOP_RE = re.compile(r"\b(?:" + "|".join(_SLOP_PHRASES) + r")\b", re.I)
# Sentence-initial filler lead-ins we can safely delete (keep the substantive clause after the comma).
_SLOP_LEADIN_RE = re.compile(
    r"(?:^|(?<=[.!?\n]))\s*(?:In (?:today'?s[^,.]{0,40}|conclusion|summary|the world of[^,.]{0,30})"
    r"|Ultimately|Needless to say|As we all know|That being said|It(?:'s| is) (?:important|worth"
    r"|crucial|essential) to (?:note|remember|mention|understand) that|It should be noted that)\s*,?\s*",
    re.I)


def slop_score(body: str) -> dict:
    """Distinctiveness grade (100 = clean): counts generic-AI-tell phrases per ~500 words and the
    number of DISTINCT tells. High slop = generic content that reads as machine-produced."""
    body = body or ""
    wc = max(1, len(_words(body)))
    hits = _SLOP_RE.findall(body)
    # normalize matched phrases for a distinct-tell count
    distinct = {h.lower().strip() for h in hits}
    density = len(hits) / (wc / 500.0)             # tells per 500 words
    # 100 - penalty; each tell per-500w costs ~12, each distinct family a touch more
    score = max(0, round(100 - density * 12 - max(0, len(distinct) - 1) * 4))
    return {"score": score, "band": _band(score), "tells": len(hits), "distinct_tells": len(distinct),
            "examples": sorted(distinct)[:12],
            "fix": ("Remove generic AI-tell phrases (formulaic openers/closers, hedges like "
                    "‘it’s important to note’, buzzwords like ‘leverage/delve/seamless’) and replace "
                    "with specific, concrete statements." if score < 80 else "")}


def scrub_slop(body: str) -> str:
    """Best-effort deterministic removal of the SAFEST sentence-initial filler lead-ins (keeps the
    real clause, re-capitalizes it). Buzzwords mid-sentence are left for the LLM revision pass, since
    deleting them blindly would break grammar."""
    if not body:
        return body
    out = body
    for _ in range(3):   # chained lead-ins: removing one can expose the next
        stripped = _SLOP_LEADIN_RE.sub("", out)
        if stripped == out:
            break
        out = stripped
    # re-capitalize the first letter of any sentence we truncated
    out = re.sub(r"(^|[.!?]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out


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
    first_para = _first_answer_para(body)
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
# A directly-quoted, ATTRIBUTED statement -- the #1 measured AI-citation lever (Princeton GEO, +41%).
# Matches a 20+ char quoted passage, or an "according to <Source>" / "<Source> reports/notes/found"
# attribution. Both together = an attributed quotation an AI answer engine can lift verbatim.
_QUOTE_STR = re.compile(r'["“][^"”\n]{20,}["”]')
_ATTRIB = re.compile(
    r'\b(?:according to|as (?:noted|reported|stated|found|estimated) (?:by|in)|per (?:the |a )?[A-Z]'
    r'|[A-Z][A-Za-z.&\'\-]{2,}(?:\s+[A-Z][A-Za-z.&\'\-]{2,})?\s+'
    r'(?:reports?|states?|notes?|found|finds?|estimates?|writes?|explains?|warns?|advises?|reported that)'
    r')\b')

# Per-content-type weight profiles (each sums to 100). Keys must exist in _geo_signal_score() below.
_GEO_PROFILES: dict[str, dict[str, int]] = {
    "blog":        {"answer_first": 16, "quotation": 12, "question_headings": 12, "stat_density": 14, "citation_density": 16, "schema": 6, "entity": 10, "freshness": 6, "chunkability": 8},
    "article":     {"answer_first": 16, "quotation": 12, "question_headings": 12, "stat_density": 14, "citation_density": 16, "schema": 6, "entity": 10, "freshness": 6, "chunkability": 8},
    "faq":         {"answer_first": 20, "question_headings": 20, "quotation": 8, "stat_density": 10, "citation_density": 12, "schema": 10, "entity": 10, "freshness": 4, "chunkability": 6},
    "white_paper": {"answer_first": 12, "quotation": 12, "stat_density": 18, "citation_density": 20, "entity": 10, "chunkability": 10, "schema": 6, "freshness": 6, "question_headings": 6},
    "landing_page":{"answer_first": 20, "comparison": 14, "entity": 14, "quotation": 8, "schema": 8, "question_headings": 12, "citation_density": 10, "freshness": 6, "chunkability": 8},
    "local_page":  {"nap": 20, "entity": 16, "answer_first": 16, "quotation": 6, "schema": 10, "reviews": 10, "freshness": 8, "question_headings": 8, "citation_density": 6},
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
    first_para = _first_answer_para(body)
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
    # quotation: attributed, directly-quoted statements -- the #1 measured AI-citation lever.
    # Count quoted passages AND source attributions; reward ~1 per 400 words (2+ on long-form).
    quotes = len(_QUOTE_STR.findall(body)) + len(_ATTRIB.findall(body))
    quotation = min(1.0, quotes / max(1.0, wc / 400.0))
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
            "quotation": quotation,
            "_suggested_schema": ("LocalBusiness" if nap >= 0.5 else "FAQPage" if qh else "Article")}


_GEO_FIX = {
    "answer_first": "Open the page (and each section) with a self-contained 40–60 word answer an AI can lift.",
    "question_headings": "Phrase H2/H3s as the real questions people ask (they map to AI prompts).",
    "stat_density": "Add a concrete, attributable statistic roughly every 150–200 words.",
    "quotation": "Quote a real statistic or authority verbatim with attribution (e.g. “…,” according to LIMRA) — attributed quotations are the strongest measured AI-citation lever (+41%).",
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
# VIDEO grader -- a video SCRIPT is graded for AI-citability (AEO/GEO) FIRST (the whole point is that
# AI answer engines surface the business), then information quality, production quality, video SEO, and
# runtime. AI engines cite video via its TRANSCRIPT, so the spoken content must be answer-first,
# entity-clear, and Q&A-structured. Weighted blend over 5 dimensions + a runtime read + a compliance note.
# ============================================================================================
_TS = re.compile(r"\b(\d{1,2}):([0-5]\d)\b")
_ONSCREEN = re.compile(r"\[\s*(?:on[-\s]?screen|visual|b-?roll|text\s*(?:card|overlay)|graphic|footage|cut to|scene)", re.I)
_NARR = re.compile(r"\b(?:narrator|v\.?o\.?|voice[-\s]?over|on[-\s]?camera|host|speaker|talent)\b", re.I)
# ideal runtime band (seconds) per rich video type
_VIDEO_LEN = {"explainer_video": (60, 180), "video_script": (45, 180), "explainer": (60, 180),
              "report_audio": (120, 600), "podcast": (300, 1500)}


def _runtime_secs(body: str) -> int:
    return max([int(m) * 60 + int(s) for m, s in _TS.findall(body or "")], default=0)


def _spoken_only(body: str) -> str:
    """Just the narration -- strip [stage directions], ## headings, and speaker labels -- because that
    is the TRANSCRIPT an AI answer engine actually reads and can cite."""
    t = re.sub(r"\[[^\]]*\]", " ", body or "")          # [ON SCREEN: ...] stage directions
    t = re.sub(r"^\s*#{1,6}.*$", " ", t, flags=re.M)     # segment headings
    t = re.sub(r"^\s*\|.*$", " ", t, flags=re.M)         # tables (production briefs)
    t = re.sub(r"^\s*\*{0,2}(?:narrator|v\.?o\.?|on[-\s]?camera|host|speaker|talent)[^:\n]{0,30}:\*{0,2}",
               " ", t, flags=re.I | re.M)                # speaker labels
    return t


def _dim(checks: list[tuple]) -> dict:
    """checks: (label, ok_bool, weight, fix) -> {score, checks[]} (weights sum to 100)."""
    score = sum(w for _, ok, w, _ in checks if ok)
    return {"score": score, "band": _band(score),
            "checks": [{"label": l, "ok": bool(ok), "points": w if ok else 0, "max": w,
                        "fix": (fix if not ok else "")} for l, ok, w, fix in checks]}


def video_score(body: str, target_query: str = "", business_name: str = "", geo: str = "",
                asset_type: str = "explainer_video") -> dict:
    """Grade a video SCRIPT across AI-citability (AEO/GEO), information quality, production quality,
    video SEO, and runtime. Returns per-dimension scorecards + a weighted overall (AI-citability
    weighted highest, per the reputation goal). Deterministic + dormant-safe."""
    body = body or ""
    low = body.lower()
    spoken = _spoken_only(body)
    qterms = _terms(target_query)
    city = (geo or "").split(",")[0].strip().lower()
    headings = _HEADING.findall(body)
    name_hits = low.count((business_name or "").lower()) if (business_name or "").strip() else 0
    runtime = _runtime_secs(body)
    onscreen = len(_ONSCREEN.findall(body))
    narr = len(_NARR.findall(body))
    seg_ts = sum(1 for h in headings if _TS.search(h))
    segments = seg_ts or len(re.findall(r"^\s*#{2,4}\s", body, re.M))
    qh = sum(1 for h in headings if h.strip().endswith("?"))
    has_faq = qh >= 1 or bool(re.search(r"\b(q ?& ?a|faq|frequently asked|common questions|questions? (?:people ask|answered))\b", low))
    # first substantive spoken line (for spoken answer-first)
    first_spoken = ""
    for para in re.split(r"\n\s*\n", spoken.strip()):
        p = para.strip(' *">\t')
        if len(_words(p)) >= 8:
            first_spoken = p
            break

    # --- 1) AEO / GEO -- AI-citability of the transcript (PRIMARY) ---
    ans_first = (bool(qterms) and sum(t in first_spoken.lower() for t in qterms) >= max(1, len(qterms) // 2)
                 and 10 <= len(_words(first_spoken)) <= 90)
    entity = (name_hits >= 3) and (not city or city in low)
    transcript = bool(re.search(r"\b(caption|closed[-\s]?caption|subtitle|srt|transcript)\b", low))
    quotable = bool(_STAT.search(spoken)) or bool(re.search(r"\b(licensed|regulated|founded|established|serves?|based in|affiliat)\b", low))
    schema = bool(re.search(r"\b(videoobject|video ?schema|clip ?schema|schema markup|structured data)\b", low))
    fresh = bool(_FRESH.search(body))
    aeo_geo = _dim([
        ("Spoken answer-first (opens with the direct answer)", ans_first, 26,
         "Have the narrator state a crisp 1-2 sentence answer to the core question in the first ~15 seconds."),
        ("Entity clarity (business + city + service, repeated)", entity, 20,
         "Say the business name + city + what it does explicitly and 3+ times."),
        ("Q&A / FAQ segment (AI extracts Q&A from transcripts)", has_faq, 16,
         "Add a short Q&A / FAQ segment answering the top questions people ask about the business."),
        ("Captions / transcript (what AI actually reads)", transcript, 16,
         "Ship closed captions / an SRT transcript -- AI answer engines read the transcript, not the pixels."),
        ("Quotable, attributable statements", quotable, 12,
         "Include a crisp, attributable, quotable line (a real stat or definitive fact) AI can lift."),
        ("VideoObject schema recommended for the embed", schema, 6,
         "Recommend VideoObject/Clip schema on the page that embeds the video."),
        ("Freshness / current-year signal", fresh, 4,
         "Add a visible last-updated / current-year cue so it reads as current."),
    ])

    # --- 2) INFORMATION quality (accurate, grounded coverage of who/what/where) ---
    covers = lambda *ws: any(w in low for w in ws)
    grounded = (name_hits >= 1) and (not city or city in low)
    info = _dim([
        ("Defines who the business is", (name_hits >= 1) and covers("team", "team of", "we are", "is a"), 18,
         "Clearly state who the business is on first mention."),
        ("Covers the core services", covers("insurance", "financial", "debt", "investment", "planning", "education"), 18,
         "Cover the main services the business offers."),
        ("States location / service area", bool(city and city in low) or covers("cincinnati", "ohio", "area", "serving"), 16,
         "Name the city / service area."),
        ("Establishes legitimacy (general licensing/affiliation)", covers("licensed", "regulated", "affiliat", "member", "registered"), 16,
         "Note (generally) that the professionals are licensed/regulated -- no specific license numbers."),
        ("Clear call to action / how to connect", covers("visit", "call", "contact", "learn more", "reach", "get a", "book"), 16,
         "End with a clear CTA (how to contact / next step)."),
        ("Grounded in real facts (not generic filler)", grounded, 16,
         "Ground the script in the business's real name + place + offerings, not generic claims."),
    ])

    # --- 3) PRODUCTION quality (shootable, well-structured) ---
    hook = len(_words(first_spoken)) >= 8 and (runtime == 0 or True)
    end_card = bool(re.search(r"\b(end ?card|logo|outro|closing|wordmark)\b", low))
    thumb = bool(re.search(r"\b(thumbnail|title card|lower third)\b", low))
    production = _dim([
        ("Opening hook", hook, 16, "Open with a hook in the first 5-10 seconds."),
        ("Segmented with timestamps", seg_ts >= 3 or segments >= 3, 18, "Break the script into 3+ timed segments."),
        ("On-screen text / visual direction", onscreen >= 3, 18, "Add on-screen text + visual/B-roll direction per segment."),
        ("Narration / dialogue present", narr >= 1, 14, "Write the actual narration/dialogue, not just directions."),
        ("Call to action", bool(re.search(r"\b(cta|call to action|visit|contact|learn more|subscribe)\b", low)), 14,
         "Add an explicit CTA."),
        ("Branded end card / outro", end_card, 10, "Add a branded end card / outro."),
        ("Thumbnail / title guidance", thumb, 10, "Include thumbnail + title guidance for the upload."),
    ])

    # --- 4) VIDEO SEO (YouTube/discovery signals) ---
    has_title = bool(re.search(r"\b(youtube title|video title|title:)\b", low)) or bool(re.match(r"^\s*#\s", body))
    has_desc = bool(re.search(r"\b(description|youtube description)\b", low))
    has_tags = bool(re.search(r"\b(tags?|keywords?)\b\s*[:|]", low))
    has_chapters = seg_ts >= 3
    kw_intro = bool(qterms) and any(t in first_spoken.lower() for t in qterms)
    video_seo = _dim([
        ("Keyword-rich title", has_title and (name_hits >= 1), 22, "Give a keyword-rich title with the business + service + city."),
        ("Description with NAP + keywords + link", has_desc, 20, "Add a description with NAP, keywords, and a link to the owned page."),
        ("Tags / keywords list", has_tags, 16, "List target tags/keywords for the upload."),
        ("Chapters / timestamps", has_chapters, 16, "Add YouTube chapters (timestamped segments)."),
        ("Captions / SRT for indexing", transcript, 16, "Upload captions/SRT -- they are indexed and read by search + AI."),
        ("Target keyword spoken in the intro", kw_intro, 10, "Say the target keyword in the spoken intro + title."),
    ])

    # --- 5) LENGTH (runtime vs the ideal band for the type) ---
    lo, hi = _VIDEO_LEN.get(asset_type, (60, 180))
    if runtime == 0:
        length = {"score": 40, "band": "weak", "runtime_secs": 0, "runtime": "unknown",
                  "note": "No timestamps found -- add segment timecodes so runtime is explicit."}
    else:
        if lo <= runtime <= hi:
            lscore = 100
        elif runtime < lo:
            lscore = max(40, round(100 * runtime / lo))
        else:
            lscore = max(50, round(100 * hi / runtime))
        length = {"score": lscore, "band": _band(lscore), "runtime_secs": runtime,
                  "runtime": f"{runtime // 60}:{runtime % 60:02d}", "ideal": f"{lo // 60}:{lo % 60:02d}-{hi // 60}:{hi % 60:02d}",
                  "note": ("in the ideal range" if lscore == 100 else "shorter than ideal" if runtime < lo else "longer than ideal")}

    W = {"aeo_geo": 0.35, "information": 0.25, "production": 0.20, "video_seo": 0.15, "length": 0.05}
    dims = {"aeo_geo": aeo_geo, "information": info, "production": production, "video_seo": video_seo, "length": length}
    overall = round(sum(dims[k]["score"] * w for k, w in W.items()))
    return {"score": overall, "band": _band(overall), "runtime_secs": runtime,
            "runtime": (length.get("runtime") if runtime else "unknown"),
            "weights": W, "dimensions": dims,
            "summary": {"AEO/GEO (AI citability)": aeo_geo["score"], "Information": info["score"],
                        "Production": production["score"], "Video SEO": video_seo["score"], "Length": length["score"]}}


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
                  asset_type: str = "", serp_benchmark: Optional[dict] = None,
                  business_id: int | None = None) -> dict:
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
        "distinctiveness": _safe("distinctiveness", lambda: slop_score(body)),
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
        out["fact_check"] = _safe("fact_check", lambda: fact_check(body, site_summary, business_id))
    return out
