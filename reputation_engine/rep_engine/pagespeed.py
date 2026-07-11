"""
Reputation Crowding-Out Engine -- PageSpeed Insights ingest + reads (technical-SEO layer)
=========================================================================================
The page-level technical-health layer the SEO gap model lacked: real Google Lighthouse scores
(Performance / SEO / Accessibility / Best-Practices) plus Core Web Vitals -- both LAB (Lighthouse)
and real-world FIELD data (Chrome UX Report) -- for any public URL.

Why it matters to the loop: a slow / CWV-failing / schema-invalid owned page silently suppresses
its own ranking and AI-citation, so a page we published to crowd out a negative may never surface.
Grading owned pages (and the competitor pages we crowd against) turns "why isn't this working" from
a guess into a specific, re-measurable finding that feeds the gap model + strategy advisor.

Free Google API. Works keyless for light use; PAGESPEED_API_KEY raises quota (25k/day). Gated by
PAGESPEED_ENABLED (default on, since it's free). Dormant-safe: every read/ingest is a no-op when
disabled, and a failed call never raises.

Run:  python -m rep_engine.pagespeed analyze --url https://example.com
      python -m rep_engine.pagespeed ingest --business-id 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

try:
    from .db import db
    from . import http as _http
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import http as _http  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("pagespeed")

_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
# Owned + competitor URLs graded per ingest; a single small pilot is a handful of pages, well under
# the 25k/day free ceiling. Configurable so a heavier account can widen it without a code change.
_MAX_URLS = int(os.getenv("PAGESPEED_MAX_URLS", "20"))
_STRATEGY = (os.getenv("PAGESPEED_STRATEGY") or "mobile").strip().lower()   # mobile | desktop


def enabled() -> bool:
    """Feature gate. Free API, so default ON -- flip PAGESPEED_ENABLED=0 to disable entirely."""
    return (os.getenv("PAGESPEED_ENABLED", "1") or "").strip().lower() not in ("0", "false", "no", "off", "")


def _api_key() -> str:
    return (os.getenv("PAGESPEED_API_KEY") or "").strip()


def _ensure_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pagespeed_scores (
                id             SERIAL PRIMARY KEY,
                business_id    INT NOT NULL,
                url            TEXT NOT NULL,
                strategy       TEXT NOT NULL DEFAULT 'mobile',
                performance    INT,          -- 0-100 Lighthouse performance
                seo            INT,          -- 0-100 Lighthouse SEO
                accessibility  INT,
                best_practices INT,
                lcp_ms         INT,          -- lab: largest contentful paint (ms)
                cls            REAL,         -- lab: cumulative layout shift
                tbt_ms         INT,          -- lab: total blocking time (ms)
                field_lcp_ms   INT,          -- field (CrUX): p75 LCP
                field_inp_ms   INT,          -- field (CrUX): p75 INP
                field_cls      REAL,         -- field (CrUX): p75 CLS
                cwv_pass       BOOLEAN,      -- field overall Core Web Vitals assessment
                is_our_content BOOLEAN NOT NULL DEFAULT FALSE,
                asset_id       INT,
                fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pagespeed_biz_url "
                     "ON pagespeed_scores(business_id, url, strategy, fetched_at DESC)")
        conn.commit()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(score):
    """Lighthouse category score is 0-1; return 0-100 int or None."""
    s = _num(score)
    return int(round(s * 100)) if s is not None else None


def analyze_url(url: str, strategy: Optional[str] = None) -> dict:
    """Run PageSpeed Insights on one URL. Returns a normalized dict of scores + Core Web Vitals,
    or {ok: False, error: ...}. Never raises."""
    strat = (strategy or _STRATEGY or "mobile").lower()
    params = {"url": url, "strategy": strat,
              "category": ["performance", "seo", "accessibility", "best-practices"]}
    key = _api_key()
    if key:
        params["key"] = key
    res = _http.request_json("GET", _API, params=params, timeout=60, max_retries=2, guard_redirects=True)
    if not res.ok or not isinstance(res.data, dict):
        return {"ok": False, "url": url, "strategy": strat,
                "error": (res.error or res.text or f"http {res.status}")[:200]}
    d = res.data
    lh = d.get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    audits = lh.get("audits") or {}

    def _lab_ms(k):
        v = _num((audits.get(k) or {}).get("numericValue"))
        return int(round(v)) if v is not None else None

    out = {
        "ok": True, "url": url, "strategy": strat,
        "performance": _pct((cats.get("performance") or {}).get("score")),
        "seo": _pct((cats.get("seo") or {}).get("score")),
        "accessibility": _pct((cats.get("accessibility") or {}).get("score")),
        "best_practices": _pct((cats.get("best-practices") or {}).get("score")),
        "lcp_ms": _lab_ms("largest-contentful-paint"),
        "cls": _num((audits.get("cumulative-layout-shift") or {}).get("numericValue")),
        "tbt_ms": _lab_ms("total-blocking-time"),
    }
    # Real-world field data (Chrome UX Report), when Google has enough traffic for this URL.
    le = d.get("loadingExperience") or {}
    metrics = le.get("metrics") or {}
    out["field_lcp_ms"] = (metrics.get("LARGEST_CONTENTFUL_PAINT_MS") or {}).get("percentile")
    out["field_inp_ms"] = (metrics.get("INTERACTION_TO_NEXT_PAINT") or {}).get("percentile")
    fcls = (metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE") or {}).get("percentile")
    out["field_cls"] = (fcls / 100.0) if isinstance(fcls, (int, float)) else None  # CrUX reports CLS*100
    overall = le.get("overall_category")   # FAST | AVERAGE | SLOW | None (insufficient data)
    out["cwv_pass"] = (overall == "FAST") if overall else None
    out["field_available"] = bool(metrics)
    return out


def _our_urls(business_id: int, conn) -> dict:
    """Published owned URLs -> asset_id, so graded pages attribute back to the content that made them."""
    out: dict[str, Optional[int]] = {}
    for r in conn.execute("SELECT id, published_url FROM assets WHERE business_id=%s AND "
                          "published_url IS NOT NULL", (business_id,)).fetchall():
        u = (r["published_url"] or "").strip()
        if u:
            out[u] = r["id"]
    return out


def _competitor_urls(business_id: int, conn, limit: int) -> list[str]:
    """Top competitor SOURCE pages we crowd against (from citation analytics), so we can grade the
    pages actually outranking us. Best-effort: table may be absent -> [] (no competitor grading)."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT url FROM citations WHERE business_id=%s AND url IS NOT NULL "
            "AND is_ours = FALSE ORDER BY url LIMIT %s", (business_id, limit)).fetchall()
        return [r["url"] for r in rows if r.get("url")]
    except Exception:  # noqa: BLE001 -- citations table optional
        return []


def ingest(business_id: int, urls: Optional[list[str]] = None, strategy: Optional[str] = None) -> dict:
    """Grade owned (+ some competitor) URLs and store results. Returns a summary.
    Dormant-safe: no-op when PAGESPEED_ENABLED is off."""
    if not enabled():
        return {"skipped": True, "reason": "PAGESPEED_ENABLED is off"}
    _ensure_table()
    strat = (strategy or _STRATEGY or "mobile").lower()
    with db() as conn:
        ours = _our_urls(business_id, conn)
        target = list(urls) if urls else list(ours.keys())
        if not urls:
            # top up with competitor pages if we have room, so the gap model can compare
            room = max(0, _MAX_URLS - len(target))
            if room:
                target += [u for u in _competitor_urls(business_id, conn, room) if u not in ours]
    target = target[:_MAX_URLS]
    if not target:
        return {"skipped": True, "reason": "no owned URLs to grade yet (publish content first)"}

    graded, failed = 0, []
    for u in target:
        r = analyze_url(u, strat)
        if not r.get("ok"):
            failed.append({"url": u, "error": r.get("error")})
            continue
        aid = ours.get(u)
        with db() as conn:
            conn.execute(
                "INSERT INTO pagespeed_scores (business_id, url, strategy, performance, seo, "
                "accessibility, best_practices, lcp_ms, cls, tbt_ms, field_lcp_ms, field_inp_ms, "
                "field_cls, cwv_pass, is_our_content, asset_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (business_id, u, strat, r["performance"], r["seo"], r["accessibility"],
                 r["best_practices"], r["lcp_ms"], r["cls"], r["tbt_ms"], r["field_lcp_ms"],
                 r["field_inp_ms"], r["field_cls"], r["cwv_pass"], aid is not None, aid))
            conn.commit()
        graded += 1
    log.info("pagespeed biz %d: graded %d/%d urls (%s)", business_id, graded, len(target), strat)
    return {"graded": graded, "failed": failed, "total": len(target), "strategy": strat}


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def latest(business_id: int, limit: int = 50) -> dict:
    """Most-recent score per URL + a rollup, for the console + gap model. Dormant-safe."""
    if not enabled():
        return {"has_data": False, "enabled": False}
    _ensure_table()
    with db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ON (url, strategy) url, strategy, performance, seo, accessibility, "
            "best_practices, lcp_ms, cls, tbt_ms, field_lcp_ms, field_inp_ms, field_cls, cwv_pass, "
            "is_our_content, asset_id, fetched_at FROM pagespeed_scores WHERE business_id=%s "
            "ORDER BY url, strategy, fetched_at DESC LIMIT %s", (business_id, limit)).fetchall()
    if not rows:
        return {"has_data": False, "enabled": True}
    pages = [{"url": r["url"], "strategy": r["strategy"], "performance": r["performance"],
              "seo": r["seo"], "accessibility": r["accessibility"], "best_practices": r["best_practices"],
              "lcp_ms": r["lcp_ms"], "cls": r["cls"], "tbt_ms": r["tbt_ms"],
              "field_lcp_ms": r["field_lcp_ms"], "field_inp_ms": r["field_inp_ms"],
              "field_cls": r["field_cls"], "cwv_pass": r["cwv_pass"],
              "is_our_content": r["is_our_content"], "asset_id": r["asset_id"],
              "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None} for r in rows]
    ours = [p for p in pages if p["is_our_content"]]
    perf = [p["performance"] for p in ours if p["performance"] is not None]
    seo = [p["seo"] for p in ours if p["seo"] is not None]
    return {"has_data": True, "enabled": True, "pages": pages,
            "owned_count": len(ours),
            "avg_performance": round(sum(perf) / len(perf)) if perf else None,
            "avg_seo": round(sum(seo) / len(seo)) if seo else None,
            "cwv_failing": [p["url"] for p in ours if p["cwv_pass"] is False],
            "slow_pages": [p["url"] for p in ours if (p["performance"] or 100) < 50]}


def technical_gaps(business_id: int) -> list[dict]:
    """Structured technical-SEO findings for the gap model / strategy advisor: owned pages that are
    slow, failing Core Web Vitals, or weak on the Lighthouse SEO category. Empty when disabled / no data."""
    snap = latest(business_id)
    if not snap.get("has_data"):
        return []
    gaps: list[dict] = []
    for p in snap["pages"]:
        if not p["is_our_content"]:
            continue
        reasons = []
        if (p["performance"] or 100) < 50:
            reasons.append(f"performance {p['performance']}/100 (slow)")
        if p["cwv_pass"] is False:
            reasons.append("fails Core Web Vitals (field data)")
        if (p["seo"] or 100) < 90:
            reasons.append(f"Lighthouse SEO {p['seo']}/100")
        if (p["lcp_ms"] or 0) > 2500:
            reasons.append(f"LCP {round((p['lcp_ms'] or 0)/1000,1)}s (>2.5s)")
        if reasons:
            gaps.append({"url": p["url"], "asset_id": p["asset_id"], "strategy": p["strategy"],
                         "issues": reasons, "performance": p["performance"], "seo": p["seo"]})
    return gaps


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="PageSpeed Insights ingest / analyze")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze"); a.add_argument("--url", required=True); a.add_argument("--strategy", default=None)
    i = sub.add_parser("ingest"); i.add_argument("--business-id", type=int, required=True)
    s = sub.add_parser("show"); s.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "analyze":
        out = analyze_url(args.url, args.strategy)
    elif args.cmd == "ingest":
        out = ingest(args.business_id)
    else:
        out = latest(args.business_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
