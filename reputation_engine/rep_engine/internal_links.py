"""
Reputation Crowding-Out Engine -- internal/external linking optimizer (Wave 2, item 9)
======================================================================================
Turns the site crawl's internal-link signal into ACTION: flags under-linked / orphan-risk pages,
and proposes contextual internal links between owned content + site pages (by topical token
overlap), with suggested anchor text. Keyless + deterministic (reads the stored site_audit +
owned assets). Auto-applying a suggestion to a WordPress page is a follow-up via the publishing
connection; for now the suggestions are surfaced for one-click human action.

    python -m rep_engine.internal_links show --business-id 2
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Optional
from urllib.parse import urlparse

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

_STOP = {"the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "www", "com", "https",
         "http", "html", "php", "index", "page", "best", "near", "your", "you"}
_UNDER_LINKED = 2  # internal_links below this = under-linked


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2 and t not in _STOP}


def _path_label(url: str) -> str:
    p = urlparse(url or "").path.rstrip("/")
    return p.split("/")[-1].replace("-", " ") or "home"


def _site_pages(business_id: int) -> list[dict]:
    with db() as conn:
        r = conn.execute("SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
                        (business_id,)).fetchone()
    if not r:
        return []
    s = r["summary"] if isinstance(r["summary"], dict) else json.loads(r["summary"])
    pages = s.get("pages") or []
    out = []
    for p in pages:
        url = p.get("url") or ""
        if not url or any(x in url for x in ("/feed", "/wp-json", "xmlrpc", ".xml", "/comments")):
            continue
        out.append({"url": url, "title": p.get("title") or _path_label(url),
                    "internal_links": int(p.get("internal_links") or 0),
                    "word_count": int(p.get("word_count") or 0),
                    "tokens": _tokens(f"{p.get('title') or ''} {_path_label(url)}")})
    return out


def _owned(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT a.title, a.published_url, a.summary, w.instruction AS wo "
            "FROM assets a LEFT JOIN work_orders w ON w.id = a.work_order_id "
            "WHERE a.business_id=%s AND a.published_url IS NOT NULL", (business_id,)).fetchall()
    return [{"title": r.get("title") or "", "url": r.get("published_url"),
             "anchor": r.get("title") or "",
             "tokens": _tokens(f"{r.get('title') or ''} {r.get('summary') or ''}")} for r in rows]


def analyze(business_id: int) -> dict:
    """Return {under_linked, suggestions, summary}. Suggestions link a relevant existing page TO an
    owned piece (and owned pieces to each other) using topical token overlap + an anchor."""
    pages = _site_pages(business_id)
    owned = _owned(business_id)
    under_linked = [{"url": p["url"], "title": p["title"], "internal_links": p["internal_links"]}
                    for p in pages if p["internal_links"] < _UNDER_LINKED]

    suggestions = []
    seen = set()
    # 1. link a related site page -> each owned piece
    for a in owned:
        if not a["tokens"]:
            continue
        ranked = sorted(pages, key=lambda p: -len(p["tokens"] & a["tokens"]))
        for p in ranked[:2]:
            ov = len(p["tokens"] & a["tokens"])
            if ov >= 1 and p["url"] != a["url"]:
                key = (p["url"], a["url"])
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append({"from": p["url"], "to": a["url"], "anchor": a["anchor"][:60],
                                    "why": f"'{p['title']}' is topically related — link to your owned page on this topic."})
    # 2. link owned pieces to each other (topic clusters)
    for i, a in enumerate(owned):
        for b in owned[i + 1:]:
            ov = len(a["tokens"] & b["tokens"])
            if ov >= 2:
                key = (a["url"], b["url"])
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append({"from": a["url"], "to": b["url"], "anchor": b["anchor"][:60],
                                    "why": "Two owned pieces on the same topic — cross-link them to build a cluster."})

    return {"under_linked": under_linked[:20], "suggestions": suggestions[:30],
            "summary": {"pages": len(pages), "owned_pieces": len(owned),
                        "under_linked": len(under_linked), "suggestions": len(suggestions)}}


def suggest_internal_links_for_draft(business_id: int, draft_body: str, target_query: str = "",
                                     limit: int = 6) -> list[dict]:
    """Concrete IN-DRAFT internal links: for each paragraph of THIS draft, the most topically-related
    existing owned page / site page to link to (anchor = target title). Suggestions only — the human
    weaves them in (no auto-injection, which would mangle the copy the reviewer is approving). Ranks
    owned pieces above generic site pages. Best-effort; returns [] when there's nothing to link to."""
    targets: list[dict] = []
    for a in _owned(business_id):
        if a.get("url") and a.get("tokens"):
            targets.append({"url": a["url"], "title": a.get("title") or _path_label(a["url"]),
                            "tokens": a["tokens"], "owned": True})
    for p in _site_pages(business_id):
        if p.get("tokens"):
            targets.append({"url": p["url"], "title": p["title"], "tokens": p["tokens"], "owned": False})
    if not targets:
        return []
    paras = [pp.strip() for pp in re.split(r"\n\s*\n", draft_body or "") if len(pp.strip()) > 40]
    out: list[dict] = []
    used: set = set()
    for idx, para in enumerate(paras):
        pt = _tokens(para)
        if not pt:
            continue
        # owned pages get a +1 tiebreak so a relevant owned piece beats an equally-relevant site page
        ranked = sorted(targets, key=lambda t: -(len(pt & t["tokens"]) + (1 if t["owned"] else 0)))
        for t in ranked:
            if len(pt & t["tokens"]) >= 2 and t["url"] not in used:
                used.add(t["url"])
                out.append({"paragraph_idx": idx, "anchor_text": t["title"][:60], "target_url": t["url"],
                            "target_title": t["title"], "priority": "high" if t["owned"] else "normal",
                            "reason": ("Link to your owned page on this topic." if t["owned"]
                                       else "Link to this related page on your site.")})
                break
        if len(out) >= limit:
            break
    return out


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Internal-linking optimizer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(analyze(args.business_id), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
