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

import re
from typing import Optional

# --- markdown/text parsing helpers ----------------------------------------------------------
_H1 = re.compile(r"^\s{0,3}#\s+\S", re.M)
_H2 = re.compile(r"^\s{0,3}##\s+\S", re.M)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+)$", re.M)
_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")          # ![alt](url)
_LINK = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)]+)\)")   # [text](url)
_STAT = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:%|percent|million|billion|k\b|years?|clients?|"
                   r"customers?|reviews?|\$)", re.I)
_SENT = re.compile(r"[.!?]+\s")


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
    try:
        from . import llm
    except ImportError:  # pragma: no cover
        import llm  # type: ignore
    import json as _json
    payload = _json.dumps({"draft": body[:6000], "known_facts": site_summary or {}}, default=str)
    res = llm.orchestrator_json(_FACTCHECK_SYSTEM, payload, tier="cheap")
    if not res or not isinstance(res, dict):
        return {"skipped": True, "claims": [], "unverified": 0}
    claims = res.get("claims") or []
    unverified = sum(1 for c in claims if c.get("status") in ("unverifiable", "contradicted"))
    return {"claims": claims[:25], "unverified": unverified}


# ============================================================================================
# combined
# ============================================================================================
def analyze_draft(body: str, *, target_query: str = "", keywords: Optional[list[str]] = None,
                  site_summary: Optional[dict] = None, with_fact_check: bool = True) -> dict:
    """Run all three scorers -> a dict suitable for content_drafts.quality_notes."""
    out = {"on_page": on_page_score(body, target_query, keywords),
           "citation_ready": citation_ready(body, target_query)}
    if with_fact_check:
        out["fact_check"] = fact_check(body, site_summary)
    return out
