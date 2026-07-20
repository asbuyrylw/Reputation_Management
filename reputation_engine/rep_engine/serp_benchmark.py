"""
SERP-competitor benchmarking (content-program Phase 3)
======================================================
For a target query, pull the top-ranking pages (Serper, cached) and derive what a piece must cover
to compete: the shared NLP terms across the ranking pages, a typical word-count target, the
questions those pages answer (People-Also-Ask), and a competitor table. This is the input that lets
the content grade be BENCHMARKED against the pages actually ranking ("beat the top-N"), not scored
in a vacuum.

Keyless/dormant-safe: with no SERPER_API_KEY, benchmark() returns {"skipped": True} and every caller
degrades to the non-benchmarked grade. Page fetching is best-effort + bounded, so a slow/blocked
competitor page can never hang or break generation.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

try:
    from . import serper as _serper
except ImportError:  # pragma: no cover
    import serper as _serper  # type: ignore

log = logging.getLogger("serp_benchmark")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_TAG = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_STRIP = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'-]+")
_STOP = set("""the a an and or but if then than of to in on for with at by from as is are was were be been
being this that these those it its it's you your we our they their he she his her not no do does did have
has had will would can could should may might must about into over under out up down more most other some
such only own same so too very just also how what why when where who which whom whose here there all any each
new get make like time people best top guide how-to vs versus review reviews using use used""".split())


def _significant_terms(texts: list[str], min_docs: int = 2, top: int = 40) -> list[str]:
    """Unigrams + bigrams that recur ACROSS competitor pages (a light NLP-term proxy)."""
    doc_uni: list[set] = []
    doc_bi: list[set] = []
    freq: Counter = Counter()
    for t in texts:
        toks = [w.lower() for w in _WORD.findall(t or "") if w.lower() not in _STOP and len(w) > 2]
        uni = set(toks)
        bi = set(f"{a} {b}" for a, b in zip(toks, toks[1:]) if a not in _STOP and b not in _STOP)
        doc_uni.append(uni)
        doc_bi.append(bi)
        for w in toks:
            freq[w] += 1
    n = len(texts) or 1
    def docs_with(term, kind):
        docs = doc_bi if kind == "bi" else doc_uni
        return sum(1 for d in docs if term in d)
    cands: list[tuple[str, int, int, int]] = []
    for term in set().union(*doc_bi) if doc_bi else set():
        d = docs_with(term, "bi")
        if d >= min_docs:
            # bigram frequency isn't tracked; approximate by the rarer constituent word's frequency
            bf = min((freq.get(w, 0) for w in term.split()), default=0)
            cands.append((term, d, 2, bf))          # prefer multi-word terms
    for term, f in freq.most_common(300):
        d = docs_with(term, "uni")
        if d >= min_docs:
            cands.append((term, d, 1, f))
    # rank by (docs-covered, is-bigram, frequency); dedup keeping first
    seen, out = set(), []
    for term, d, kind, f in sorted(cands, key=lambda x: (x[1], x[2], x[3]), reverse=True):
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= top:
            break
    return out


def _fetch_text(url: str, timeout: int = 12) -> Optional[str]:
    """Best-effort plain-text of a page. Bounded + never raises out."""
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        if r.status_code != 200 or not r.text:
            return None
        html = _TAG.sub(" ", r.text)
        text = _STRIP.sub(" ", html)
        return re.sub(r"\s+", " ", text).strip()[:60000]
    except Exception as e:  # noqa: BLE001
        log.debug("serp fetch %s failed: %s", url, e)
        return None


def benchmark(query: str, *, top_n: int = 10, fetch_pages: int = 3) -> dict:
    """Return the SERP benchmark for a query, or {skipped} when Serper isn't configured."""
    q = (query or "").strip()
    if not q:
        return {"skipped": True, "reason": "no query"}
    data = _serper.cached_post("search", {"q": q, "num": max(top_n, 10)})
    if not data:
        return {"skipped": True, "reason": "SERPER_API_KEY not set"}
    organic = (data.get("organic") or [])[:top_n]
    competitors = [{"title": o.get("title"), "link": o.get("link"),
                    "snippet": o.get("snippet"), "position": o.get("position")} for o in organic]
    questions = [x.get("question") for x in (data.get("peopleAlsoAsk") or []) if x.get("question")]
    questions += [r.get("query") for r in (data.get("relatedSearches") or []) if r.get("query")][:6]
    # fetch a few ranking pages for real word counts + term extraction
    texts, wordcounts = [], []
    for c in competitors[:max(0, fetch_pages)]:
        if not c.get("link"):
            continue
        txt = _fetch_text(c["link"])
        if txt:
            wc = len(_WORD.findall(txt))
            wordcounts.append(wc)
            c["words"] = wc
            texts.append(txt)
    # if no page fetched, fall back to titles+snippets for term signal
    if not texts:
        texts = [f"{c.get('title','')} {c.get('snippet','')}" for c in competitors]
    avg_words = round(sum(wordcounts) / len(wordcounts)) if wordcounts else None
    terms = _significant_terms(texts, min_docs=2 if len(texts) > 1 else 1, top=40)
    return {"query": q, "competitors": competitors, "avg_word_count": avg_words,
            "terms": terms, "questions": questions[:12], "pages_fetched": len(wordcounts),
            "skipped": False}
