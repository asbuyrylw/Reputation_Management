"""
GSC full-surface: URL Inspection harvest + Sitemap management
=============================================================
indexing.py already calls the URL Inspection API but keeps only coverageState. This module harvests
the ~95% of the payload we were discarding -- googleCanonical vs userCanonical (canonical loss that
silently sinks owned pages), richResultsResult (structured-data / schema validity, the exact FAQ /
Article / LocalBusiness markup that drives AI Overview + LLM extraction), indexingState /
robotsTxtState / pageFetchState / lastCrawlTime (WHY a fix isn't live, not just that it isn't) --
and turns each into a specific, re-measurable technical finding that feeds the gap model + advisor.

It also wires the unused Sitemaps resource: submit our owned-content feed as a sitemap and read the
per-sitemap submitted / indexed / error counts -- the Google-discovery lever we lacked (IndexNow
covers Bing/Yandex, not Google).

Everything is fail-safe: no GSC connection => {skipped}; a failed inspect => that URL is recorded as
error, never raises. Read-only diagnostics on the owner's own verified property (no compliance surface).

Run:  python -m rep_engine.gsc_inspect inspect --business-id 1
      python -m rep_engine.gsc_inspect sitemaps --business-id 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Optional

try:
    from .db import db
    from .connections import vault as _vault
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from connections import vault as _vault  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("gsc_inspect")

_MAX_URLS = int(os.getenv("GSC_INSPECT_MAX_URLS", "25"))   # URL Inspection quota is 2000/day/site


def _provider():
    try:
        from .connections.providers import google_search_console as g
    except ImportError:  # pragma: no cover
        from connections.providers import google_search_console as g  # type: ignore
    return g


def _connection(business_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT id, account_ref, meta FROM platform_connections WHERE business_id=%s AND "
            "kind='google_search_console' AND status='active' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
    if not row:
        return None
    creds = _vault.credentials(row["id"], business_id)
    if not creds or not creds.get("access_token"):
        return None
    prop = (row.get("meta") or {}).get("gsc_property") or row.get("account_ref")
    if not prop:
        return None
    return {"token": creds["access_token"], "property": prop}


def _owned_urls(business_id: int, limit: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, published_url FROM assets WHERE business_id=%s AND published_url IS NOT NULL "
            "AND published_status='live' ORDER BY published_at DESC NULLS LAST, id DESC LIMIT %s",
            (business_id, limit)).fetchall()
    return [{"asset_id": r["id"], "title": r["title"], "url": r["published_url"]} for r in rows]


def _ensure_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gsc_url_inspection (
                id                 SERIAL PRIMARY KEY,
                business_id        INT NOT NULL,
                url                TEXT NOT NULL,
                asset_id           INT,
                verdict            TEXT,     -- PASS | PARTIAL | FAIL | NEUTRAL
                coverage_state     TEXT,     -- "Submitted and indexed" | "Crawled - currently not indexed" | ...
                indexing_state     TEXT,     -- INDEXING_ALLOWED | BLOCKED_BY_META_TAG | ...
                robots_state       TEXT,     -- ALLOWED | DISALLOWED
                fetch_state        TEXT,     -- SUCCESSFUL | SOFT_404 | ...
                last_crawl         TEXT,
                google_canonical   TEXT,
                user_canonical     TEXT,
                canonical_mismatch BOOLEAN NOT NULL DEFAULT FALSE,
                is_indexed         BOOLEAN,
                rich_verdict       TEXT,     -- richResultsResult.verdict PASS | FAIL
                schema_issues      JSONB DEFAULT '[]'::jsonb,
                mobile_verdict     TEXT,
                inspected_at       TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gsc_inspect_biz "
                     "ON gsc_url_inspection(business_id, url, inspected_at DESC)")
        conn.commit()


def _parse(result: dict) -> dict:
    """Flatten the URL Inspection inspectionResult into the fields we store + derive findings."""
    idx = result.get("indexStatusResult") or {}
    rich = result.get("richResultsResult") or {}
    mob = result.get("mobileUsabilityResult") or {}
    gcanon = idx.get("googleCanonical") or ""
    ucanon = idx.get("userCanonical") or ""
    coverage = idx.get("coverageState") or ""
    canonical_mismatch = bool(gcanon and ucanon and gcanon.rstrip("/") != ucanon.rstrip("/"))
    is_indexed = ("indexed" in coverage.lower() and "not" not in coverage.lower()) or idx.get("verdict") == "PASS"
    # collect ERROR-severity schema issues (structured-data that Google rejects -> no rich results)
    schema_issues: list[dict] = []
    for det in (rich.get("detectedItems") or []):
        rtype = det.get("richResultType") or "item"
        for it in (det.get("items") or []):
            for iss in (it.get("issues") or []):
                if (iss.get("severity") or "").upper() in ("ERROR", "WARNING"):
                    schema_issues.append({"type": rtype, "name": it.get("name"),
                                          "severity": iss.get("severity"),
                                          "message": iss.get("issueMessage")})
    return {
        "verdict": idx.get("verdict"), "coverage_state": coverage,
        "indexing_state": idx.get("indexingState"), "robots_state": idx.get("robotsTxtState"),
        "fetch_state": idx.get("pageFetchState"), "last_crawl": idx.get("lastCrawlTime"),
        "google_canonical": gcanon or None, "user_canonical": ucanon or None,
        "canonical_mismatch": canonical_mismatch, "is_indexed": bool(is_indexed),
        "rich_verdict": rich.get("verdict"), "schema_issues": schema_issues,
        "mobile_verdict": mob.get("verdict"),
    }


def inspect(business_id: int, limit: Optional[int] = None) -> dict:
    """Inspect owned URLs, harvest the full payload, store it, and return a summary + findings.
    Fail-safe: {skipped} without a GSC connection."""
    conn_info = _connection(business_id)
    urls = _owned_urls(business_id, limit or _MAX_URLS)
    if not conn_info:
        return {"skipped": True, "reason": "no active Google Search Console connection/property",
                "urls": len(urls)}
    if not urls:
        return {"skipped": True, "reason": "no live owned URLs to inspect yet"}
    _ensure_table()
    g = _provider()
    token, prop = conn_info["token"], conn_info["property"]
    inspected, errors = 0, 0
    for a in urls:
        r = g.inspect_url(token, prop, a["url"])
        if not r.get("ok"):
            errors += 1
            continue
        p = _parse(r["result"])
        with db() as conn:
            conn.execute(
                "INSERT INTO gsc_url_inspection (business_id, url, asset_id, verdict, coverage_state, "
                "indexing_state, robots_state, fetch_state, last_crawl, google_canonical, user_canonical, "
                "canonical_mismatch, is_indexed, rich_verdict, schema_issues, mobile_verdict) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (business_id, a["url"], a["asset_id"], p["verdict"], p["coverage_state"],
                 p["indexing_state"], p["robots_state"], p["fetch_state"], p["last_crawl"],
                 p["google_canonical"], p["user_canonical"], p["canonical_mismatch"], p["is_indexed"],
                 p["rich_verdict"], json.dumps(p["schema_issues"]), p["mobile_verdict"]))
            conn.commit()
        inspected += 1
    log.info("gsc inspect biz %d: %d inspected, %d errors", business_id, inspected, errors)
    return {"inspected": inspected, "errors": errors, "urls": len(urls), **latest(business_id)}


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def latest(business_id: int) -> dict:
    """Most-recent inspection per URL + a rollup for the console + gap model + advisor."""
    _ensure_table()
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ON (url) url, asset_id, verdict, coverage_state, indexing_state, "
            "robots_state, fetch_state, last_crawl, google_canonical, user_canonical, "
            "canonical_mismatch, is_indexed, rich_verdict, schema_issues, mobile_verdict, inspected_at "
            "FROM gsc_url_inspection WHERE business_id=%s ORDER BY url, inspected_at DESC",
            (business_id,)).fetchall()
    if not rows:
        return {"has_data": False, "pages": []}
    pages = []
    for r in rows:
        si = r["schema_issues"] if isinstance(r["schema_issues"], list) else json.loads(r["schema_issues"] or "[]")
        pages.append({"url": r["url"], "asset_id": r["asset_id"], "verdict": r["verdict"],
                      "coverage_state": r["coverage_state"], "indexing_state": r["indexing_state"],
                      "robots_state": r["robots_state"], "fetch_state": r["fetch_state"],
                      "last_crawl": r["last_crawl"], "google_canonical": r["google_canonical"],
                      "user_canonical": r["user_canonical"], "canonical_mismatch": r["canonical_mismatch"],
                      "is_indexed": r["is_indexed"], "rich_verdict": r["rich_verdict"],
                      "schema_issues": si, "mobile_verdict": r["mobile_verdict"],
                      "inspected_at": r["inspected_at"].isoformat() if r["inspected_at"] else None})
    return {
        "has_data": True, "pages": pages,
        "checked": len(pages),
        "indexed": sum(1 for p in pages if p["is_indexed"]),
        "not_indexed": [p["url"] for p in pages if not p["is_indexed"]],
        "canonical_loss": [p["url"] for p in pages if p["canonical_mismatch"]],
        "schema_invalid": [p["url"] for p in pages if p["rich_verdict"] == "FAIL" or p["schema_issues"]],
    }


def technical_gaps(business_id: int) -> list[dict]:
    """Structured index/canonical/schema findings for the gap model + advisor. Empty when no data."""
    snap = latest(business_id)
    if not snap.get("has_data"):
        return []
    gaps: list[dict] = []
    for p in snap["pages"]:
        reasons = []
        if p["canonical_mismatch"]:
            reasons.append(f"canonical lost to {p['google_canonical']} (Google prefers a different URL)")
        if not p["is_indexed"] and p["coverage_state"]:
            reasons.append(f"not indexed: {p['coverage_state']}")
        if p["robots_state"] == "DISALLOWED":
            reasons.append("blocked by robots.txt")
        if p["fetch_state"] and p["fetch_state"] != "SUCCESSFUL":
            reasons.append(f"page fetch: {p['fetch_state']}")
        if p["rich_verdict"] == "FAIL" or p["schema_issues"]:
            n = len(p["schema_issues"])
            reasons.append(f"invalid structured data ({n} issue{'s' if n != 1 else ''})")
        if reasons:
            gaps.append({"url": p["url"], "asset_id": p["asset_id"], "issues": reasons})
    return gaps


# ---------------------------------------------------------------------------
# sitemaps
# ---------------------------------------------------------------------------
def sitemaps(business_id: int) -> dict:
    """List submitted sitemaps + per-sitemap submitted/indexed/error counts. Fail-safe."""
    conn_info = _connection(business_id)
    if not conn_info:
        return {"skipped": True, "reason": "no active Google Search Console connection/property", "sitemaps": []}
    res = _provider().list_sitemaps(conn_info["token"], conn_info["property"])
    return res


def submit_content_feed(business_id: int, feed_url: Optional[str] = None) -> dict:
    """Submit our owned-content RSS/sitemap feed to Google so new content is discovered faster
    (complements IndexNow, which Google ignores). Fail-safe."""
    conn_info = _connection(business_id)
    if not conn_info:
        return {"skipped": True, "reason": "no active Google Search Console connection/property"}
    if not feed_url:
        origin = (os.getenv("PUBLIC_APP_ORIGIN") or "").rstrip("/")
        feed_url = f"{origin}/api/businesses/{business_id}/content-feed.xml" if origin else None
    if not feed_url:
        return {"skipped": True, "reason": "no PUBLIC_APP_ORIGIN set to build the feed URL"}
    return {"feed_url": feed_url, **_provider().submit_sitemap(conn_info["token"], conn_info["property"], feed_url)}


def run(business_id: int) -> dict:
    """Job entry: harvest URL inspections + list sitemaps (+ submit the content feed)."""
    out = {"inspect": inspect(business_id), "sitemaps": sitemaps(business_id)}
    if (os.getenv("GSC_SUBMIT_SITEMAP", "1") or "").strip().lower() not in ("0", "false", "no", "off"):
        out["submit"] = submit_content_feed(business_id)
    return out


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="GSC full-surface: URL Inspection + Sitemaps")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("inspect", "sitemaps", "run", "show"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "inspect":
        out = inspect(args.business_id)
    elif args.cmd == "sitemaps":
        out = sitemaps(args.business_id)
    elif args.cmd == "show":
        out = latest(args.business_id)
    else:
        out = run(args.business_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
