"""
Reputation Crowding-Out Engine -- own-content indexing engine (Wave 3, item 11; WHITE-HAT)
==========================================================================================
Helps Google + AI engines DISCOVER and index the content WE published (owned pages only — never
manipulative link-farm indexing). Three legitimate mechanisms:

  * RSS feed  -- a feed of newly published owned URLs (search engines + aggregators poll it).
  * Ping      -- notify WebSub/PubSubHubbub + Google's ping endpoint when new content ships.
  * Index status -- via GSC URL Inspection, report which owned URLs Google has actually indexed,
                    and surface the unindexed ones for a one-click "Request indexing" in GSC
                    (Google no longer exposes general programmatic submission, so we're honest:
                    we detect + surface, the human clicks Request indexing).

Keyless-safe: RSS + ping always work; the index-status check no-ops without a GSC connection.

    python -m rep_engine.indexing run --business-id 2
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

try:
    from .db import db
    from . import http as _http
    from .connections import vault as _vault
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import http as _http  # type: ignore
    from connections import vault as _vault  # type: ignore

log = logging.getLogger("indexing")
GSC_INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def _owned_urls(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, published_url, published_at FROM assets "
            "WHERE business_id=%s AND published_url IS NOT NULL AND published_status='live' "
            "ORDER BY published_at DESC NULLS LAST, id DESC", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def rss(business_id: int) -> str:
    """An RSS 2.0 feed of owned published URLs (for search-engine discovery)."""
    with db() as conn:
        b = conn.execute("SELECT name, domain FROM businesses WHERE id=%s", (business_id,)).fetchone()
    name = (b or {}).get("name") or "Business"
    site = (b or {}).get("domain") or ""
    items = []
    for a in _owned_urls(business_id):
        pub = a["published_at"].strftime("%a, %d %b %Y %H:%M:%S +0000") if a.get("published_at") else ""
        items.append(
            f"<item><title>{_xml(a.get('title') or '')}</title>"
            f"<link>{_xml(a['published_url'])}</link>"
            f"<guid>{_xml(a['published_url'])}</guid>"
            f"{f'<pubDate>{pub}</pubDate>' if pub else ''}</item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{_xml(name)} — new content</title><link>{_xml(site)}</link>"
            f"<description>Newly published content from {_xml(name)}</description>"
            + "".join(items) + "</channel></rss>")


def _xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ping(feed_url: Optional[str] = None) -> dict:
    """Notify WebSub hubs of new content (white-hat discovery accelerant). Keyless."""
    if not feed_url:
        return {"pinged": 0, "reason": "no public feed url configured (set PUBLIC_APP_ORIGIN + serve the feed)"}
    hubs = ["https://pubsubhubbub.appspot.com/", "https://websubhub.com/hub"]
    ok = 0
    for hub in hubs:
        try:
            res = _http.request_json("POST", hub, data={"hub.mode": "publish", "hub.url": feed_url},
                                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                                     timeout=10, max_retries=1, parse_json=False, guard_redirects=True)
            ok += 1 if res.ok else 0
        except Exception:  # noqa: BLE001
            pass
    return {"pinged": ok, "hubs": len(hubs)}


def _gsc_token(business_id: int) -> Optional[str]:
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM platform_connections WHERE business_id=%s AND kind='google_search_console' "
            "AND status='active' ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    if not row:
        return None
    creds = _vault.credentials(row["id"], business_id)
    return (creds or {}).get("access_token")


def _gsc_property(business_id: int) -> Optional[str]:
    with db() as conn:
        row = conn.execute(
            "SELECT account_ref, meta FROM platform_connections WHERE business_id=%s AND "
            "kind='google_search_console' AND status='active' ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    if not row:
        return None
    return (row.get("meta") or {}).get("gsc_property") or row.get("account_ref")


def check_index_status(business_id: int, limit: int = 25) -> dict:
    """GSC URL Inspection for each owned URL -> which Google has indexed + which need a manual
    'Request indexing'. Keyless-safe (skips without a GSC connection)."""
    token = _gsc_token(business_id)
    prop = _gsc_property(business_id)
    urls = _owned_urls(business_id)
    if not token or not prop:
        return {"skipped": True, "reason": "no Google Search Console connection", "urls": len(urls)}
    indexed, not_indexed = [], []
    for a in urls[:limit]:
        res = _http.request_json("POST", GSC_INSPECT_URL,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                 json={"inspectionUrl": a["published_url"], "siteUrl": prop},
                                 timeout=20, max_retries=1, guard_redirects=True)
        verdict = None
        if res.ok and isinstance(res.data, dict):
            verdict = (((res.data.get("inspectionResult") or {}).get("indexStatusResult") or {})
                       .get("coverageState"))
        entry = {"url": a["published_url"], "title": a.get("title"), "coverage": verdict}
        if verdict and "indexed" in verdict.lower() and "not" not in verdict.lower():
            indexed.append(entry)
        else:
            not_indexed.append(entry)
    return {"indexed": indexed, "not_indexed": not_indexed,
            "summary": {"checked": len(indexed) + len(not_indexed), "indexed": len(indexed),
                        "needs_request": len(not_indexed)}}


def run(business_id: int) -> dict:
    """Job entry: ping search engines about the owned-content feed + report index status."""
    import os
    origin = (os.getenv("PUBLIC_APP_ORIGIN") or "").rstrip("/")
    feed_url = f"{origin}/api/businesses/{business_id}/content-feed.xml" if origin else None
    out = {"feed_url": feed_url, "ping": ping(feed_url), "index": check_index_status(business_id)}
    log.info("indexing run biz %d: %s", business_id, {"ping": out["ping"]})
    return out


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Own-content indexing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "rss", "status"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "rss":
        print(rss(args.business_id))
    else:
        print(json.dumps(run(args.business_id) if args.cmd == "run" else check_index_status(args.business_id), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
