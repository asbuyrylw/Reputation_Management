"""
Source-material AUTO-INGEST (Phase G.1 / UX-2)
==============================================
Makes the grounding corpus REAL without the owner pasting anything. The client's own website is the
richest, always-available source of true facts about them; the site crawler already fetches and
extracts each page's main text (for the site audit) -- this turns that extracted text into
`source_documents` so `grounding_retrieval.has_grounding()` / `retrieve()` actually find facts, and
every generated draft is grounded in the client's real pages instead of generic web filler.

Refresh semantics (idempotent): a re-sync REPLACES the previously-ingested set for a given source
(e.g. all `site_crawl` docs) and re-inserts the current pages, so re-running never duplicates and the
corpus stays current with the live site. Manually-uploaded docs (`source_type='upload'`) are never
touched -- only the auto-ingested source being refreshed.

Fail-loud / dormant-safe, consistent with source_material: a not-yet-migrated table returns a no-op
result; a real DB error is logged and raised (a broken ingest must not look like "the site had no
content"). A crawl that reaches zero usable pages is reported honestly (ingested=0), not hidden.
"""
from __future__ import annotations

import logging
from typing import Optional

try:
    from .db import db
    from . import site_crawl as _sc
    from . import source_material as _sm
except ImportError:  # pragma: no cover -- direct-run fallback
    from db import db  # type: ignore
    import site_crawl as _sc  # type: ignore
    import source_material as _sm  # type: ignore

log = logging.getLogger("source_ingest")

SITE_CRAWL_SOURCE = "site_crawl"      # source_type stamped on auto-ingested website pages
_MAX_DOC_CHARS = 8000                 # cap per page so one huge page can't dominate the corpus
_DEFAULT_MIN_WORDS = 120              # skip thin pages (nav stubs, empty templates)
_DEFAULT_MAX_PAGES = 20               # keep the corpus focused on the client's main content


def _seed_for(business: dict) -> Optional[str]:
    domain = (business.get("domain") or "").strip()
    if not domain:
        return None
    return domain if domain.startswith("http") else f"https://{domain}"


def _clear_source(business_id: int, source_type: str) -> int:
    """Delete the prior auto-ingested docs for this source so a re-sync doesn't duplicate them.
    Returns the number removed. (Manual 'upload' docs are a different source_type -- untouched.)"""
    with db() as conn:
        n = conn.execute("DELETE FROM source_documents WHERE business_id=%s AND source_type=%s",
                         (business_id, source_type)).rowcount
        conn.commit()
    return int(n or 0)


def ingest_from_pages(business_id: int, pages: list, *, min_words: int = _DEFAULT_MIN_WORDS,
                      created_by: Optional[int] = None) -> dict:
    """(Re)ingest an ALREADY-CRAWLED list of PageAudit into source_documents as `site_crawl`
    grounding. Idempotent: replaces the prior site_crawl set with the current pages, so the pipeline
    (which crawls once for the site audit) can feed the corpus WITHOUT a second crawl.

    Returns {ingested, skipped, pages_crawled, replaced, source_type}."""
    pages = pages or []

    # Content pages only: fetched OK, not a system/asset artifact, and substantive.
    candidates = []
    for p in pages:
        url = getattr(p, "url", "") or ""
        text = (getattr(p, "main_text", "") or "").strip()
        if getattr(p, "status", 0) != 200 or _sc._is_crawl_artifact(url):
            continue
        if getattr(p, "word_count", 0) < min_words or not text:
            continue
        candidates.append(p)

    # De-dupe by URL; order by richness (word_count) so the most substantive pages win when trimmed.
    seen: set[str] = set()
    uniq = []
    for p in sorted(candidates, key=lambda x: -(getattr(x, "word_count", 0) or 0)):
        u = (getattr(p, "url", "") or "").split("#")[0]
        if u in seen:
            continue
        seen.add(u)
        uniq.append(p)

    # Refresh: clear the prior site_crawl set, then insert the current pages. The live site is
    # authoritative, so replacing stale docs is correct even when the new crawl yields fewer pages.
    removed = _clear_source(business_id, SITE_CRAWL_SOURCE)
    ingested = 0
    for p in uniq:
        title = (getattr(p, "title", "") or "").strip() or (getattr(p, "url", "") or "").split("//")[-1][:120]
        content = (getattr(p, "main_text", "") or "").strip()[:_MAX_DOC_CHARS]
        doc_id = _sm.add_document(business_id, content, title=title,
                                  source_type=SITE_CRAWL_SOURCE, source_url=getattr(p, "url", None),
                                  created_by=created_by)
        if doc_id:
            ingested += 1

    log.info("source_ingest business=%s: pages=%d ingested=%d (replaced %d prior)",
             business_id, len(pages), ingested, removed)
    return {
        "source_type": SITE_CRAWL_SOURCE,
        "pages_crawled": len(pages),
        "ingested": ingested,
        "skipped": len(pages) - ingested,
        "replaced": removed,
    }


def ingest_site(business_id: int, *, max_pages: int = _DEFAULT_MAX_PAGES,
                min_words: int = _DEFAULT_MIN_WORDS, created_by: Optional[int] = None) -> dict:
    """Crawl the business's website and (re)ingest each content page's main text into
    source_documents as `site_crawl` grounding. Standalone path for the console's "Sync website"
    button (the pipeline uses ingest_from_pages to avoid a second crawl).

    Returns the ingest_from_pages summary (raises SystemExit if no domain)."""
    with db() as conn:
        b = conn.execute("SELECT id, domain FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not b:
        raise SystemExit(f"No business id {business_id}")
    seed = _seed_for(dict(b))
    if not seed:
        raise SystemExit("Business has no domain set -- add a website to auto-ingest source material.")

    # Reuse the audit crawler (SSRF-guarded, robots-aware, Trafilatura main-text). No semantic targets
    # needed for ingest -- we want the page TEXT, not the scorecard.
    pages = _sc.crawl_site(seed, max_pages=max_pages, targets=None)
    return ingest_from_pages(business_id, pages, min_words=min_words, created_by=created_by)
