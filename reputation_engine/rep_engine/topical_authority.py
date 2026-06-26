"""
Reputation Crowding-Out Engine -- topical authority / content intelligence (Wave 2, item 8)
===========================================================================================
MarketMuse-style: cluster the business's target keywords into TOPIC CLUSTERS (a pillar + spokes),
score how well current owned content covers each cluster, and surface "what to write next to own
this topic." Deterministic + keyless (token-overlap clustering over target_keywords), so it works
the moment keyword research has run. Feeds the content-briefs page + the gap model.

    python -m rep_engine.topical_authority show --business-id 2
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

_STOP = {"the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "best", "near", "me",
         "top", "how", "what", "is", "are", "with", "your", "you", "my", "do", "does", "vs"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2 and t not in _STOP}


def _load_keywords(business_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT keyword, kind, intent, priority, search_volume FROM target_keywords "
            "WHERE business_id=%s ORDER BY priority DESC NULLS LAST, keyword", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def _published(business_id: int) -> list[set]:
    """Token sets of published/owned content (title + target_query) for coverage scoring."""
    with db() as conn:
        rows = conn.execute(
            "SELECT title, summary AS q FROM assets WHERE business_id=%s "
            "UNION ALL SELECT title, target_query AS q FROM content_drafts WHERE business_id=%s AND status='approved'",
            (business_id, business_id)).fetchall()
    return [_tokens(f"{r.get('title') or ''} {r.get('q') or ''}") for r in rows]


def clusters(business_id: int) -> dict:
    """Greedy token-overlap clustering of target keywords into pillar/spoke topics, scored by
    current owned-content coverage. Returns {clusters: [...], summary}."""
    kws = _load_keywords(business_id)
    if not kws:
        return {"clusters": [], "summary": {"keywords": 0, "topics": 0, "uncovered": 0}}
    published = _published(business_id)

    # Strip the business name + geo tokens from clustering, else every keyword sharing the city or
    # brand name collapses into one giant topic. (They stay in the keyword text; just not used to merge.)
    with db() as conn:
        b = conn.execute("SELECT name, geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
    generic = _tokens(f"{(b or {}).get('name') or ''} {(b or {}).get('geo') or ''}") if b else set()

    # Greedy clustering requiring TWO shared significant tokens to merge -- the sweet spot between
    # merging everything that shares one common word (one giant cluster) and splitting every keyword
    # into its own topic. Keywords processed highest-priority-first so cluster themes are stable.
    cl: list[dict] = []  # each: {tokens:set, members:[kw...]}
    for k in kws:
        toks = _tokens(k["keyword"]) - generic
        if not toks:
            toks = _tokens(k["keyword"])  # all-generic keyword (e.g. just the city) -> keep as-is
        if not toks:
            continue
        best, best_ov = None, 1  # init 1 so only an overlap >= 2 wins
        for c in cl:
            ov = len(toks & c["tokens"])
            if ov > best_ov:
                best, best_ov = c, ov
        if best:
            best["members"].append(k)
            best["tokens"] |= toks
        else:
            cl.append({"tokens": set(toks), "members": [k]})

    out = []
    for c in cl:
        members = sorted(c["members"], key=lambda m: -(m.get("priority") or 0))
        pillar = members[0]
        theme_tokens = c["tokens"]
        # coverage: how many owned pieces share >=2 tokens with the cluster theme
        covered_by = sum(1 for p in published if len(p & theme_tokens) >= 2)
        vol = sum(int(m.get("search_volume") or 0) for m in c["members"])
        out.append({
            "topic": pillar["keyword"],
            "pillar": pillar["keyword"],
            "spokes": [m["keyword"] for m in members[1:]],
            "keyword_count": len(members),
            "total_search_volume": vol or None,
            "owned_pieces": covered_by,
            "needs_content": covered_by == 0,
            "priority": pillar.get("priority") or 0,
        })
    # rank: uncovered + high-priority + big clusters first
    out.sort(key=lambda c: (0 if c["needs_content"] else 1, -(c["priority"]), -c["keyword_count"]))
    uncovered = sum(1 for c in out if c["needs_content"])
    return {"clusters": out, "summary": {"keywords": len(kws), "topics": len(out), "uncovered": uncovered}}


def by_intent(business_id: int) -> dict:
    """Map target keywords by SEARCH INTENT + flag which intents lack owned content (Wave 5, item 19
    "Data Cube"-lite). Keywords already carry an intent from keyword research."""
    kws = _load_keywords(business_id)
    published = _published(business_id)
    groups: dict[str, list[str]] = {}
    for k in kws:
        it = (k.get("intent") or "unknown").lower()
        groups.setdefault(it, []).append(k["keyword"])
    out = []
    for it, kwl in groups.items():
        toks: set[str] = set()
        for kw in kwl:
            toks |= _tokens(kw)
        covered = sum(1 for p in published if len(p & toks) >= 2)
        out.append({"intent": it, "keywords": len(kwl), "examples": kwl[:5],
                    "owned_pieces": covered, "needs_content": covered == 0})
    out.sort(key=lambda x: -x["keywords"])
    return {"by_intent": out, "summary": {"intents": len(out),
                                          "uncovered": sum(1 for g in out if g["needs_content"])}}


def next_to_write(business_id: int, limit: int = 5) -> list[dict]:
    """The highest-leverage uncovered topics to write next (pillar-first)."""
    cs = clusters(business_id)["clusters"]
    return [{"topic": c["topic"], "covers_keywords": c["keyword_count"],
             "spokes": c["spokes"][:6], "why": "No owned content covers this topic cluster yet."}
            for c in cs if c["needs_content"]][:limit]


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="Topical authority clustering")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show"); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(clusters(args.business_id), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
