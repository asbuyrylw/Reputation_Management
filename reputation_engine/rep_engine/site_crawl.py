"""
Reputation Crowding-Out Engine -- Module 3: Technical Site-Crawl Audit
=====================================================================
Crawls the business's own domain and produces an on-site SEO / structure audit
that feeds the SAME gap model the AI-state audit feeds. Two layers:

  1. Crawl (no paid tools): fetch pages, parse titles/meta/headings/canonicals,
     detect JSON-LD schema presence, find internal links, flag thin content.
  2. Optional Lighthouse pass (open-source) for performance / Core Web Vitals /
     SEO score, if the `lighthouse` CLI is installed.

Output is stored on the latest audit_run and merged into schema_gaps /
missing_owned_content so Module 2 (strategy_generator) can act on it.

Why this matters for AI visibility: answer engines extract facts most reliably
from fast, well-structured pages with clean schema. On-site gaps directly limit
how well the accurate narrative can be surfaced.

Run:
    python -m rep_engine.site_crawl crawl --business-id 1 --max-pages 40
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib import robotparser


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

try:
    from . import http as _http
except ImportError:  # pragma: no cover
    import http as _http  # type: ignore

try:
    from . import netguard as _netguard
except ImportError:  # pragma: no cover
    import netguard as _netguard  # type: ignore

try:
    from .textutils import split_terms
except ImportError:  # pragma: no cover
    from textutils import split_terms  # type: ignore

# Optional fast HTML parser; falls back to regex if unavailable.
try:
    from selectolax.parser import HTMLParser as _HTMLParser  # type: ignore
    _HAS_PARSER = True
except ImportError:  # pragma: no cover
    _HTMLParser = None
    _HAS_PARSER = False

# Optional Trafilatura: when installed, gives much cleaner main-text (strips nav/boilerplate)
# than our parser/regex extraction. Purely additive -- if absent, extraction is unchanged.
try:
    import trafilatura  # type: ignore
except ImportError:  # pragma: no cover
    trafilatura = None

# Optional richer SEO analysis via pyseoanalyzer's Page parser, run on HTML we
# fetch ourselves (with our resilient http layer) -- NOT its fragile networking.
try:
    from pyseoanalyzer.page import Page as _SeoPage  # type: ignore
    _HAS_SEO = True
except ImportError:  # pragma: no cover
    _SeoPage = None
    _HAS_SEO = False

# Non-content system/asset URLs (WordPress feeds, xmlrpc, wp-json/admin/includes/content,
# oembed, comment-reply links, CSS/JS/feed files). These are crawl artifacts -- never real
# "thin content pages" and never content opportunities -- so they must not pollute the gap
# model's missing_owned_content or the SEO view's thin-page list.
_CRAWL_ARTIFACT_RE = re.compile(
    r"(?:"
    r"/feed/?$|/comments/feed|/trackback/?$|"
    r"xmlrpc\.php|wp-(?:json|admin|includes|content)|oembed|"
    r"\?replytocom=|"
    r"\.(?:css|js|json|xml|rss|atom|map|ico|png|jpe?g|gif|svg|webp|woff2?|ttf)(?:\?|$)"
    r")",
    re.IGNORECASE,
)


def _is_crawl_artifact(url: str) -> bool:
    """True for non-content system/asset URLs that should never be treated as a thin
    content page or turned into a content opportunity."""
    return bool(_CRAWL_ARTIFACT_RE.search(url or ""))
USE_SEO_ANALYZER = os.getenv("CRAWL_USE_PYSEO", "1") != "0"   # PH 4: 0 to disable

# Firecrawl: optional JS-rendering fetch layer. When configured, the crawler fetches
# the fully-rendered HTML via Firecrawl (handling SPAs / client-side rendered sites
# that our plain HTTP layer would see as near-empty), then runs the SAME extraction
# and pyseo enrichment on it. Falls back to plain HTTP when not configured or on error.
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")              # PH 5
FIRECRAWL_BASE = os.getenv("FIRECRAWL_BASE", "https://api.firecrawl.dev")  # PH 6
# Only use Firecrawl when a plain fetch looks JS-rendered (thin body) -> save credits.
FIRECRAWL_MODE = os.getenv("CRAWL_FIRECRAWL_MODE", "auto")          # auto | always | off  (PH 7)
_FIRECRAWL_MIN_WORDS = 120  # below this on a 200 page, suspect JS render -> retry via Firecrawl


def _firecrawl_fetch(url: str) -> Optional[str]:
    """Fetch fully-rendered HTML via Firecrawl. Returns HTML or None on failure/not-configured."""
    if not FIRECRAWL_API_KEY or FIRECRAWL_MODE == "off":
        return None
    try:
        _netguard.assert_url_allowed(url)
    except _netguard.UnsafeURLError as e:
        log.warning("Firecrawl target blocked by SSRF guard (%s): %s", url, e)
        return None
    res = _http.request_json(
        "POST", f"{FIRECRAWL_BASE}/v2/scrape",
        headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["html"], "onlyMainContent": False},
        timeout=60, max_retries=2,
    )
    if res.failed:
        log.warning("Firecrawl fetch failed for %s: %s -- falling back to plain HTTP", url, res.error)
        return None
    data = res.data or {}
    # v2 returns {"success":true,"data":{"html":...,"markdown":...,"metadata":{...}}}
    inner = data.get("data", data)
    html = inner.get("html") or inner.get("rawHtml") or ""
    return html or None


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("site_crawl")

USER_AGENT = os.getenv("CRAWL_UA", "ReputationEngineBot/1.0 (+audit)")                     # PH 2
THIN_CONTENT_WORDS = 300  # pages under this word count are flagged thin
RESPECT_ROBOTS = os.getenv("CRAWL_RESPECT_ROBOTS", "1") != "0"   # PH 3: set 0 to disable
# Per-page wall-clock budget across retries so one slow page can't stall the crawl
# (bounds total fetch time incl. backoff; "0"/"" disables). See http.request_json.
_PAGE_DEADLINE_RAW = os.getenv("CRAWL_PAGE_DEADLINE_S", "45")
PAGE_FETCH_DEADLINE = float(_PAGE_DEADLINE_RAW) if _PAGE_DEADLINE_RAW not in ("", "0") else None




# ----------------------------------------------------------------------------
# Lightweight crawler (no external paid tools)
# ----------------------------------------------------------------------------
@dataclass
class PageAudit:
    url: str
    status: int = 0
    title: str = ""
    title_len: int = 0
    meta_description: str = ""
    meta_len: int = 0
    h1_count: int = 0
    word_count: int = 0
    has_canonical: bool = False
    schema_types: list[str] = field(default_factory=list)
    internal_links: int = 0
    issues: list[str] = field(default_factory=list)
    keywords: list = field(default_factory=list)        # top keywords (pyseo)
    seo_warnings: list = field(default_factory=list)     # richer warnings (pyseo)
    semantic: dict = field(default_factory=dict)         # semantic-depth scorecard (Module 12)
    main_text: str = ""                                  # extracted body text (for grounding ingest)


def _same_host(seed: str, url: str) -> bool:
    return urlparse(seed).netloc == urlparse(url).netloc


def _text_words(html: str) -> int:
    # strip scripts/styles/tags, count words
    no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", no_script)
    return len(text.split())


def _find(pattern: str, html: str, flags=re.IGNORECASE | re.DOTALL) -> str:
    m = re.search(pattern, html, flags)
    return (m.group(1).strip() if m and m.groups() else "")


def _schema_types(html: str) -> list[str]:
    types: list[str] = []
    for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            html, re.DOTALL | re.IGNORECASE):
        try:
            data = json.loads(block.strip())
            for obj in (data if isinstance(data, list) else [data]):
                t = obj.get("@type") if isinstance(obj, dict) else None
                if isinstance(t, list):
                    types.extend(t)
                elif t:
                    types.append(t)
        except json.JSONDecodeError:
            types.append("INVALID_JSON_LD")
    return types


def _main_text(html: str) -> Optional[str]:
    """Optional cleaner main-content text via Trafilatura (strips nav/boilerplate/footers).
    Returns None when trafilatura isn't installed or finds no extractable main content, so the
    caller falls back to the existing extraction unchanged."""
    if trafilatura is None:
        return None
    try:
        txt = trafilatura.extract(html)
    except Exception as e:  # noqa: BLE001 -- optional dependency must never break extraction
        log.debug("trafilatura extract failed: %s", e)
        return None
    txt = (txt or "").strip()
    return txt or None


def _extract(html: str) -> dict:
    """Extract page fields. Uses selectolax (robust HTML parsing) when available,
    falling back to regex. Robust parsing matters because real-world markup breaks
    naive regex, and JS-heavy pages need accurate text counts to avoid false
    'thin_content' flags. When Trafilatura is installed, its cleaner main-text replaces
    the boilerplate-laden body text (and word count); otherwise behavior is unchanged."""
    # Optional Trafilatura main-content text -- None when unavailable/empty (fall back below).
    main = _main_text(html)
    if _HAS_PARSER:
        try:
            tree = _HTMLParser(html)
            title_node = tree.css_first("title")
            title = title_node.text(strip=True) if title_node else ""
            meta = ""
            for node in tree.css('meta[name="description"]'):
                meta = node.attributes.get("content", "") or ""
                if meta:
                    break
            h1s = tree.css("h1")
            canonical = bool(tree.css_first('link[rel="canonical"]'))
            # strip script/style for word count
            for tag in tree.css("script, style"):
                tag.decompose()
            body = tree.body
            text = body.text(separator=" ", strip=True) if body else tree.text(separator=" ", strip=True)
            # Prefer Trafilatura's cleaner main-text for word count + the semantic scorer when present.
            if main is not None:
                text = main
            words = len(text.split())
            hrefs = [a.attributes.get("href", "") for a in tree.css("a[href]")]
            return {"title": title, "meta": meta, "h1_count": len(h1s),
                    "canonical": canonical, "words": words, "text": text,
                    "hrefs": [h for h in hrefs if h], "schema": _schema_types(html)}
        except Exception as e:  # noqa: BLE001 -- fall back to regex on any parser error
            log.warning("selectolax parse failed (%s); using regex fallback", e)
    # regex fallback
    no_tags = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                                              flags=re.DOTALL | re.IGNORECASE))
    # Prefer Trafilatura's cleaner main-text for word count + the semantic scorer when present.
    text = main if main is not None else " ".join(no_tags.split())
    return {
        "title": _find(r"<title[^>]*>(.*?)</title>", html),
        "meta": _find(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', html),
        "h1_count": len(re.findall(r"<h1[\s>]", html, re.IGNORECASE)),
        "canonical": bool(re.search(r'<link[^>]*rel=["\']canonical["\']', html, re.IGNORECASE)),
        "words": len(text.split()) if main is not None else _text_words(html),
        "text": text,
        "hrefs": re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE),
        "schema": _schema_types(html),
    }


def _load_robots(seed_url: str):
    """Return a configured RobotFileParser, or None if robots can't be read /
    robots respect is disabled."""
    if not RESPECT_ROBOTS:
        return None
    p = urlparse(seed_url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        _netguard.assert_url_allowed(robots_url)
    except _netguard.UnsafeURLError as e:
        log.warning("robots.txt fetch blocked by SSRF guard (%s): %s", robots_url, e)
        return None
    rp = robotparser.RobotFileParser()
    res = _http.request_json("GET", robots_url, parse_json=False, max_retries=1, timeout=15)
    if res.ok and res.text:
        try:
            rp.parse(res.text.splitlines())
            return rp
        except Exception:  # noqa: BLE001
            return None
    return None  # no robots.txt -> allow (standard behavior)


def _seo_enrich(pa: "PageAudit", url: str, html: str) -> None:
    """Enrich a PageAudit with pyseoanalyzer's richer analysis, run on HTML we
    already fetched (so we keep our resilient fetch layer). Best-effort: any
    failure leaves the base extraction intact."""
    if not (_HAS_SEO and USE_SEO_ANALYZER):
        return
    try:
        from urllib.parse import urlparse as _up
        p = _up(url)
        base = f"{p.scheme}://{p.netloc}"   # pyseo Page expects a string here
        page = _SeoPage(url=url, base_domain=base, analyze_headings=True,
                        analyze_extra_tags=False)
        page.analyze(raw_html=html)
        d = page.as_dict()
        kw = d.get("keywords") or []
        # pyseo may yield dicts {"word","count"} or (count, word) tuples; normalize
        norm = []
        for k in kw:
            if isinstance(k, dict):
                norm.append({"word": k.get("word"), "count": k.get("count")})
            elif isinstance(k, (list, tuple)) and len(k) == 2:
                count, word = k
                norm.append({"word": word, "count": count})
            else:
                norm.append({"word": str(k), "count": None})
        pa.keywords = norm[:15]
        pa.seo_warnings = list(d.get("warnings") or [])
        if not pa.word_count and d.get("word_count"):
            pa.word_count = int(d["word_count"])
    except Exception as e:  # noqa: BLE001
        log.debug("pyseo enrich skipped for %s: %s", url, e)


def audit_page(seed: str, url: str, targets: dict | None = None) -> tuple[PageAudit, list[str]]:
    pa = PageAudit(url=url)
    try:
        _netguard.assert_url_allowed(url)
    except _netguard.UnsafeURLError as e:
        pa.issues.append(f"fetch_failed: blocked_by_ssrf_guard: {e}")
        return pa, []
    res = _http.request_json("GET", url, headers={"User-Agent": USER_AGENT},
                             parse_json=False, timeout=20, guard_redirects=True,
                             deadline=PAGE_FETCH_DEADLINE)
    if res.failed:
        pa.issues.append(f"fetch_failed: {res.error}")
        return pa, []
    pa.status = res.status or 0
    html = res.text
    if pa.status != 200:
        pa.issues.append(f"status_{pa.status}")
        return pa, []

    ex = _extract(html)

    # JS-render detection: if a 200 page is suspiciously thin (likely client-side
    # rendered), re-fetch the fully-rendered HTML via Firecrawl and re-extract.
    # 'always' forces it; 'auto' only does it when the plain fetch looks empty.
    used_firecrawl = False
    if FIRECRAWL_MODE == "always" or (FIRECRAWL_MODE == "auto" and ex["words"] < _FIRECRAWL_MIN_WORDS):
        rendered = _firecrawl_fetch(url)
        if rendered:
            html = rendered
            ex = _extract(html)
            used_firecrawl = True
            log.info("Firecrawl rendered %s (words %d -> %d)", url,
                     0 if "words" not in ex else ex["words"], ex["words"])

    pa.title = ex["title"]
    pa.title_len = len(pa.title)
    pa.meta_description = ex["meta"]
    pa.meta_len = len(pa.meta_description)
    pa.h1_count = ex["h1_count"]
    pa.word_count = ex["words"]
    pa.has_canonical = ex["canonical"]
    pa.schema_types = ex["schema"]
    pa.main_text = (ex.get("text") or "").strip()   # captured for source-material grounding ingest
    if used_firecrawl:
        pa.issues.append("rendered_via_firecrawl")  # informational, not a defect

    # optional richer SEO analysis on the same HTML (keeps our fetch layer)
    _seo_enrich(pa, url, html)

    # semantic-depth scorecard (Module 12): the on-page signals research links to
    # AI citation. Uses business targets when provided; otherwise a generic pass.
    try:
        from . import semantic_depth as _sd
        targets = targets or {}
        pa.semantic = _sd.analyze_text(
            ex.get("text", ""), title=pa.title,
            target_terms=targets.get("terms", []),
            target_questions=targets.get("questions", []),
            target_query=targets.get("query", ""),
            html=html,
        )
    except Exception as e:  # noqa: BLE001
        log.debug("semantic-depth skipped for %s: %s", url, e)

    abs_links = [urljoin(url, l) for l in ex["hrefs"]]
    internal = [l for l in abs_links if _same_host(seed, l) and urlparse(l).scheme in ("http", "https")]
    pa.internal_links = len(internal)

    # per-page issue flags
    if not pa.title:
        pa.issues.append("missing_title")
    elif pa.title_len > 65:
        pa.issues.append("title_too_long")
    if not pa.meta_description:
        pa.issues.append("missing_meta_description")
    if pa.h1_count == 0:
        pa.issues.append("missing_h1")
    elif pa.h1_count > 1:
        pa.issues.append("multiple_h1")
    if pa.word_count < THIN_CONTENT_WORDS:
        pa.issues.append("thin_content")
    if not pa.has_canonical:
        pa.issues.append("missing_canonical")
    if not pa.schema_types:
        pa.issues.append("no_schema")

    next_urls = []
    for l in internal:
        clean = l.split("#")[0]
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|mp4|css|js)$", clean, re.IGNORECASE):
            continue
        # Don't spend crawl budget on WordPress system URLs (feeds, wp-json, xmlrpc, oembed).
        # On a small WP site these dominate the link graph and crowd real pages out of the
        # capped queue, which is why a one-page site showed "only 2 content pages."
        if _is_crawl_artifact(clean):
            continue
        next_urls.append(clean)
    return pa, next_urls


def crawl_site(seed_url: str, max_pages: int = 40, targets: dict | None = None) -> list[PageAudit]:
    seen: set[str] = set()
    queue = [seed_url.rstrip("/")]
    results: list[PageAudit] = []
    rp = _load_robots(seed_url)
    if rp:
        log.info("robots.txt loaded; disallowed paths will be skipped.")
    skipped_robots = 0
    while queue and len(results) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if rp and not rp.can_fetch(USER_AGENT, url):
            skipped_robots += 1
            continue
        pa, next_urls = audit_page(seed_url, url, targets)
        results.append(pa)
        for n in next_urls:
            if n not in seen and len(seen) + len(queue) < max_pages * 3:
                queue.append(n)
        time.sleep(0.3)
    if skipped_robots:
        log.info("Skipped %d URLs disallowed by robots.txt", skipped_robots)
    log.info("Crawled %d pages of %s", len(results), seed_url)
    return results


# ----------------------------------------------------------------------------
# Optional Lighthouse pass (open-source) -- only if CLI present
# ----------------------------------------------------------------------------
def lighthouse(url: str) -> dict:
    if not shutil.which("lighthouse"):
        log.info("lighthouse CLI not found; skipping performance pass. "
                 "Install: npm i -g lighthouse")
        return {}
    try:
        _netguard.assert_url_allowed(url)
    except _netguard.UnsafeURLError as e:
        log.warning("lighthouse target blocked by SSRF guard (%s): %s", url, e)
        return {}
    try:
        out = subprocess.run(
            ["lighthouse", url, "--quiet", "--chrome-flags=--headless",
             "--only-categories=performance,seo,accessibility,best-practices",
             "--output=json", "--output-path=stdout"],
            capture_output=True, text=True, timeout=180,
        )
        data = json.loads(out.stdout)
        cats = data.get("categories", {})
        return {k: round((cats[k]["score"] or 0) * 100) for k in cats}
    except Exception as e:  # noqa: BLE001
        log.warning("lighthouse failed: %s", e)
        return {}


# ----------------------------------------------------------------------------
# Roll crawl results into the shared gap-model inputs
# ----------------------------------------------------------------------------
def summarize(results: list[PageAudit], lh: dict) -> dict:
    total = len(results)
    schema_present = {t for pa in results for t in pa.schema_types}
    desired_schema = {"Organization", "FAQPage", "Person", "Review", "LocalBusiness"}
    schema_gaps = sorted(desired_schema - schema_present)
    # exclude WordPress/system crawl artifacts (feeds, xmlrpc, wp-json, CSS/JS) -- they are
    # not real content pages, so flagging them as "thin" is noise in the SEO view and the gap
    # model (the validation found ~5 such junk items polluting missing_owned_content).
    thin = [pa.url for pa in results if "thin_content" in pa.issues and not _is_crawl_artifact(pa.url)]
    no_meta = [pa.url for pa in results if "missing_meta_description" in pa.issues
               and not _is_crawl_artifact(pa.url)]
    # markers that are informational, not defects -- kept on the page record but
    # not counted as issues (so reports don't show them as problems).
    _INFO_MARKERS = {"rendered_via_firecrawl"}
    issue_counts: dict[str, int] = {}
    for pa in results:
        for i in pa.issues:
            if i in _INFO_MARKERS:
                continue
            issue_counts[i] = issue_counts.get(i, 0) + 1
    rendered_count = sum(1 for pa in results if "rendered_via_firecrawl" in pa.issues)
    # average semantic citation-readiness across pages that produced a scorecard
    sem_scores = [pa.semantic.get("citation_readiness_score") for pa in results
                  if isinstance(pa.semantic, dict) and pa.semantic.get("citation_readiness_score") is not None]
    avg_semantic = round(sum(sem_scores) / len(sem_scores), 1) if sem_scores else None
    # collect the most common missing entities across pages (crowding-out targets)
    missing_counter: dict[str, int] = {}
    for pa in results:
        if isinstance(pa.semantic, dict):
            for term in (pa.semantic.get("entity_coverage", {}) or {}).get("missing", []) or []:
                missing_counter[term] = missing_counter.get(term, 0) + 1
    top_missing = sorted(missing_counter, key=missing_counter.get, reverse=True)[:10]
    # Aggregate the per-page GEO signals (front-loading, question coverage, freshness, title
    # alignment) so the gap model can ACT on them -- not just the single avg readiness number.
    # These are the signals 2026 GEO research links to being CITED by answer engines.
    def _avg(vals):
        v = [x for x in vals if isinstance(x, (int, float))]
        return round(sum(v) / len(v), 3) if v else None
    sems = [pa.semantic for pa in results if isinstance(pa.semantic, dict) and pa.semantic]
    geo_signals = {
        "avg_front_loading": _avg([s.get("front_loading") for s in sems]),
        "avg_title_alignment": _avg([s.get("title_alignment") for s in sems]),
        "avg_question_coverage": _avg([(s.get("question_coverage") or {}).get("rate") for s in sems]),
        "pages_with_freshness_date": sum(1 for s in sems if (s.get("freshness") or {}).get("has_date")),
        "pages_scored": len(sems),
        "low_readiness_pages": sum(1 for s in sems
                                   if (s.get("citation_readiness_score") or 100) < 60),
    }
    return {
        "pages_crawled": total,
        "lighthouse": lh,
        "schema_present": sorted(schema_present),
        "schema_gaps": schema_gaps,
        "thin_pages": thin,
        "pages_missing_meta": no_meta,
        "issue_counts": issue_counts,
        "rendered_via_firecrawl": rendered_count,
        "avg_semantic_readiness": avg_semantic,
        "geo_signals": geo_signals,
        "top_missing_entities": top_missing,
        "pages": [pa.__dict__ for pa in results],
    }


def merge_into_gap_inputs(business_id: int, summary: dict) -> None:
    """Attach the technical summary to the latest audit_run and extend the
    most recent gap_model's schema_gaps / missing_owned_content."""
    with db() as conn:
        run = conn.execute(
            "SELECT id FROM audit_runs WHERE business_id=%s AND kind='ai_audit' AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1", (business_id,),
        ).fetchone()
        biz = conn.execute("SELECT contested_terms FROM businesses WHERE id=%s",
                           (business_id,)).fetchone()
        contested = [t.lower() for t in split_terms(biz["contested_terms"]) if t] if biz else []
        conn.execute(
            "CREATE TABLE IF NOT EXISTS site_audits ("
            "id BIGSERIAL PRIMARY KEY, business_id BIGINT, run_id BIGINT, "
            "summary JSONB, created_at TIMESTAMPTZ DEFAULT now())"
        )
        conn.execute(
            "INSERT INTO site_audits (business_id, run_id, summary) VALUES (%s,%s,%s)",
            (business_id, run["id"] if run else None, json.dumps(summary)),
        )
        # extend latest gap model if present
        gm = conn.execute(
            "SELECT id, model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,),
        ).fetchone()
        if gm:
            model = gm["model"] if isinstance(gm["model"], dict) else json.loads(gm["model"])
            existing = set(model.get("schema_gaps", []) or [])
            model["schema_gaps"] = sorted(existing | set(summary["schema_gaps"]))
            # IDEMPOTENT merge: _remerge (run_full) and every re-crawl call this again, so append ONLY
            # topics not already present -- otherwise the same "Expand thin page X" / "Add coverage of
            # 'Y'" entries pile up in the gap model on every cycle (unbounded duplicate drift).
            moc = model.get("missing_owned_content", []) or []
            _seen_topics = {(m.get("topic") or "").strip().lower() for m in moc if isinstance(m, dict)}

            def _add_moc(entry: dict) -> None:
                t = (entry.get("topic") or "").strip().lower()
                if t and t not in _seen_topics:
                    _seen_topics.add(t)
                    moc.append(entry)

            for url in summary["thin_pages"][:5]:
                _add_moc({"topic": f"Expand thin page {url}", "asset_type": "article",
                          "why": "Page below content threshold; weak for retrieval/extraction."})
            # semantic-depth findings: missing entities become content opportunities -- but
            # NEVER auto-propose a page targeting a CONTESTED term (e.g. "pyramid scheme",
            # "scam"). A naive keyword page reinforces the very negative association we are
            # crowding out; the right response to a contested topic is a legitimacy /
            # transparency / corroboration asset, which the gap-model LLM proposes separately.
            for term in (summary.get("top_missing_entities") or [])[:8]:
                tl = (term or "").lower()
                if any(ct in tl or tl in ct for ct in contested):
                    continue
                _add_moc({"topic": f"Add/strengthen coverage of '{term}'", "asset_type": "article",
                          "why": "Topic AI answers expect but the site under-covers "
                                 "(semantic-depth gap; entity coverage drives AI citation)."})
            model["missing_owned_content"] = moc
            if summary.get("avg_semantic_readiness") is not None:
                model["avg_semantic_readiness"] = summary["avg_semantic_readiness"]
            conn.execute("UPDATE gap_models SET model=%s WHERE id=%s",
                         (json.dumps(model), gm["id"]))
        conn.commit()
    log.info("Site audit merged (run_id=%s).", run["id"] if run else None)


def crawl_cmd(business_id: int, max_pages: int) -> None:
    with db() as conn:
        b = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not b:
        raise SystemExit(f"No business id {business_id}")
    domain = b.get("domain") or ""
    if not domain:
        raise SystemExit("Business has no domain set.")
    seed = domain if domain.startswith("http") else f"https://{domain}"
    try:
        _netguard.assert_url_allowed(seed)
    except _netguard.UnsafeURLError as e:
        raise SystemExit(f"Business domain rejected by SSRF guard: {e}")
    # build semantic targets from the business: services/geo/contested terms as the
    # entities AI answers would expect; the prompt battery as target questions.
    def _split(v):
        return split_terms(v, extra_seps=";")   # seeds split on ';' AND ',' (see textutils)
    terms = _split(b.get("services")) + _split(b.get("geo")) + _split(b.get("contested_terms"))
    terms = [t for t in terms if t][:20]
    try:
        from . import ai_state_audit as _m
        questions = [p for p in _m.build_prompt_battery(dict(b))][:12]
    except Exception:  # noqa: BLE001
        questions = []
    targets = {"terms": terms, "questions": questions,
               "query": f"{b.get('services','')} {b.get('geo','')}".strip()}
    results = crawl_site(seed, max_pages=max_pages, targets=targets)
    lh = lighthouse(seed)
    summary = summarize(results, lh)
    merge_into_gap_inputs(business_id, summary)
    # Auto-ingest the pages we just crawled into the grounding corpus (source_documents), so content
    # generation is grounded in the client's real site without a second crawl. Best-effort: a corpus
    # write must never fail the site audit itself.
    try:
        from . import source_ingest as _si
        ing = _si.ingest_from_pages(business_id, results)
        log.info("site_crawl: ingested %d page(s) into grounding corpus", ing.get("ingested", 0))
    except Exception as e:  # noqa: BLE001 -- ingest is a bonus; the audit is the job
        log.warning("site_crawl: grounding ingest skipped: %s", e)
    print(json.dumps({k: v for k, v in summary.items() if k != "pages"}, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description="Technical site-crawl audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("crawl")
    pc.add_argument("--business-id", type=int, required=True)
    pc.add_argument("--max-pages", type=int, default=40)
    args = ap.parse_args()
    if args.cmd == "crawl":
        crawl_cmd(args.business_id, args.max_pages)


if __name__ == "__main__":
    main()
