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
_STAT = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|k\b|years?|clients?|"
                   r"customers?|reviews?|\$)", re.I)
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
                  geo: str = "", keyword_intent: str = "") -> dict:
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
        "intent_serp": _safe("intent_serp", lambda: intent_and_serp(target_query, keyword_intent)),
    }
    if neuron_terms:
        out["term_coverage"] = _safe("term_coverage", lambda: term_coverage(body, neuron_terms))
    if with_fact_check:
        out["fact_check"] = _safe("fact_check", lambda: fact_check(body, site_summary))
    return out
