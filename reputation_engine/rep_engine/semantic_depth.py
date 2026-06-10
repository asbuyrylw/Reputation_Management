"""
Reputation Crowding-Out Engine -- Module 12: Semantic Depth Analyzer
====================================================================
Scores a page on the on-page signals that 2026 GEO measurement research found
actually correlate with being CITED by AI engines -- the depth our basic crawler
(title/meta/word-count/schema) was missing.

What it measures (grounded in the research, not guesswork):
  - ENTITY / TOPIC COVERAGE: of the terms an AI answer about this topic would
    expect, how many does the page actually cover? (fan-out / entity coverage was
    found more predictive than single-keyword density.)
  - TITLE-TO-QUERY ALIGNMENT: does the title/H1 align with the target query?
    (title-to-query alignment is a citation-selection signal.)
  - FRONT-LOADING: how much of the answer-relevant content sits in the first 30%
    of the page? (~44% of citations draw from the first 30% of a page.)
  - FRESHNESS: does the page expose a recent date signal? (content updated within
    ~3 months is cited roughly twice as often.)
  - LEXICAL BREADTH: distinct meaningful terms / lexical fields -- a proxy for
    semantic richness vs. thin or repetitive copy.
  - QUESTION COVERAGE: does the page answer the actual questions people ask?
    (supporting-question coverage drives fan-out citations.)

NOT overweighted on purpose: backlinks and schema markup -- the same research found
neither moved AI citation share within a retrieved corpus. We still note schema for
classic SEO, but it does NOT inflate the citation-readiness score here.

This is heuristic and transparent (no LLM call required), so it is cheap and runs on
the HTML the crawler already fetched. An optional LLM pass can enrich entity lists.

Usage (standalone or via crawler):
    from rep_engine.semantic_depth import analyze_text
    result = analyze_text(text, title, target_terms, target_questions, html=html)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# common English stopwords (kept small; this is a proxy, not full NLP)
_STOP = set("""a an and are as at be by for from has have in is it its of on or that the to
was were will with this these those you your we our they their he she his her them but not
can could should would may might must do does did done how what when where which who why
into over under about above below more most some any all each other than then them""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),                       # ISO
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+(20\d{2})\b", re.I),
    re.compile(r'datetime="(20\d{2})-(\d{2})-(\d{2})', re.I),
    re.compile(r'"datePublished"\s*:\s*"(20\d{2})-(\d{2})-(\d{2})', re.I),
    re.compile(r'"dateModified"\s*:\s*"(20\d{2})-(\d{2})-(\d{2})', re.I),
]


def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP and len(w) > 2]


def _coverage(text_tokens: set[str], target_terms: list[str]) -> dict:
    """How many target entity/topic terms appear on the page."""
    if not target_terms:
        return {"covered": [], "missing": [], "rate": None}
    covered, missing = [], []
    for term in target_terms:
        t = term.lower().strip()
        # multi-word term: require all significant words present
        words = [w for w in _WORD.findall(t) if w.lower() not in _STOP]
        present = all(w.lower() in text_tokens for w in words) if words else False
        (covered if present else missing).append(term)
    rate = round(len(covered) / len(target_terms), 4) if target_terms else None
    return {"covered": covered, "missing": missing, "rate": rate}


def _title_alignment(title: str, target_query: str) -> float:
    """Overlap of significant query words present in the title (0..1)."""
    if not title or not target_query:
        return 0.0
    q = {w.lower() for w in _WORD.findall(target_query) if w.lower() not in _STOP}
    t = {w.lower() for w in _WORD.findall(title)}
    if not q:
        return 0.0
    return round(len(q & t) / len(q), 4)


def _front_load(text: str, target_terms: list[str]) -> float:
    """Share of target-term hits that occur in the first 30% of the body (0..1)."""
    toks = [w.lower() for w in _WORD.findall(text or "")]
    if not toks or not target_terms:
        return 0.0
    cut = max(1, int(len(toks) * 0.30))
    head = set(toks[:cut])
    term_words = []
    for term in target_terms:
        term_words += [w.lower() for w in _WORD.findall(term) if w.lower() not in _STOP]
    if not term_words:
        return 0.0
    hits_head = sum(1 for w in term_words if w in head)
    hits_total = sum(1 for w in term_words if w in set(toks))
    return round(hits_head / hits_total, 4) if hits_total else 0.0


def _freshness(text: str, html: str = "") -> dict:
    """Most recent year-month found via date signals; months-old estimate."""
    blob = (html or "") + "\n" + (text or "")
    best = None
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(blob):
            try:
                year = int(m.group(1))
                month = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2).isdigit() else 1
            except (ValueError, IndexError):
                continue
            if 2015 <= year <= datetime.now().year + 1:
                cand = (year, month)
                if best is None or cand > best:
                    best = cand
    if not best:
        return {"has_date": False, "months_old": None}
    now = datetime.now(timezone.utc)
    months_old = (now.year - best[0]) * 12 + (now.month - best[1])
    return {"has_date": True, "latest": f"{best[0]:04d}-{best[1]:02d}", "months_old": max(0, months_old)}


def _question_coverage(text: str, questions: list[str]) -> dict:
    """How many target questions the page appears to address (keyword-overlap proxy)."""
    if not questions:
        return {"answered": [], "unanswered": [], "rate": None}
    toks = set(_tokens(text))
    answered, unanswered = [], []
    for q in questions:
        qwords = {w.lower() for w in _WORD.findall(q) if w.lower() not in _STOP and len(w) > 2}
        if qwords and len(qwords & toks) / len(qwords) >= 0.6:
            answered.append(q)
        else:
            unanswered.append(q)
    return {"answered": answered, "unanswered": unanswered,
            "rate": round(len(answered) / len(questions), 4) if questions else None}


def analyze_text(text: str, title: str = "", target_terms: list[str] | None = None,
                 target_questions: list[str] | None = None, target_query: str = "",
                 html: str = "") -> dict:
    """Return a semantic-depth scorecard for a page's text. All inputs optional;
    the more context (target terms/questions/query) supplied, the richer the score."""
    target_terms = target_terms or []
    target_questions = target_questions or []
    toks = _tokens(text)
    tok_set = set(toks)
    total = len(toks)
    unique = len(tok_set)

    cov = _coverage(tok_set, target_terms)
    qcov = _question_coverage(text, target_questions)
    align = _title_alignment(title, target_query or " ".join(target_terms[:6]))
    front = _front_load(text, target_terms)
    fresh = _freshness(text, html)
    lexical_breadth = round(unique / total, 4) if total else 0.0   # type-token ratio proxy

    # citation-readiness score (0..100): weighted toward what research says moves
    # AI citations. Backlinks/schema deliberately NOT in this score.
    parts = []
    weights = []
    if cov["rate"] is not None:
        parts.append(cov["rate"]); weights.append(0.30)
    if qcov["rate"] is not None:
        parts.append(qcov["rate"]); weights.append(0.20)
    parts.append(align); weights.append(0.15)
    parts.append(front); weights.append(0.15)
    # freshness sub-score: 1.0 if <=3 months, decaying to 0 by ~24 months
    if fresh["has_date"] and fresh["months_old"] is not None:
        fscore = max(0.0, min(1.0, 1.0 - (fresh["months_old"] - 3) / 21)) if fresh["months_old"] > 3 else 1.0
    else:
        fscore = 0.3   # unknown date = mild penalty, not zero
    parts.append(fscore); weights.append(0.12)
    parts.append(min(1.0, lexical_breadth * 2.5)); weights.append(0.08)  # breadth, capped

    score = round(100 * sum(p * w for p, w in zip(parts, weights)) / sum(weights), 1) if weights else 0.0

    # actionable recommendations, ordered by impact
    recs = []
    if cov["missing"]:
        recs.append(f"Add coverage of missing topics/entities: {', '.join(cov['missing'][:8])}")
    if qcov["unanswered"]:
        recs.append(f"Directly answer these questions on-page: {', '.join(qcov['unanswered'][:5])}")
    if align < 0.6 and (target_query or target_terms):
        recs.append("Align the title/H1 more closely with the target query wording.")
    if front < 0.5 and target_terms:
        recs.append("Move key answer content into the first 30% of the page (AI cites the top of pages).")
    if fresh["has_date"] and (fresh["months_old"] or 0) > 6:
        recs.append(f"Refresh the page — last date signal is ~{fresh['months_old']} months old "
                    "(recent content is cited ~2x as often).")
    if not fresh["has_date"]:
        recs.append("Expose a visible last-updated date (helps freshness signals).")
    if lexical_breadth < 0.25 and total > 100:
        recs.append("Content is lexically repetitive; broaden the supporting vocabulary/subtopics.")

    return {
        "citation_readiness_score": score,
        "word_count": total,
        "entity_coverage": cov,
        "question_coverage": qcov,
        "title_alignment": align,
        "front_loading": front,
        "freshness": fresh,
        "lexical_breadth": lexical_breadth,
        "recommendations": recs,
        "method": ("Heuristic scorecard weighted toward signals 2026 GEO research links "
                   "to AI citation (entity/question coverage, title alignment, front-loading, "
                   "freshness). Backlinks and schema are intentionally excluded from this score "
                   "because controlled studies found they did not move AI citation share."),
    }
