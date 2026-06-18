"""
Reputation Crowding-Out Engine -- Module 12: Local SEO rank tracking
====================================================================
Reputation crowding-out wins AI ANSWERS. This wins the adjacent battle a local
business actually feels in the wallet: ranking on the FIRST PAGE of Google -- and in
the local map ("places") pack -- for the same category-local searches a nearby
customer types: "financial advisors in Cincinnati, OH", "financial advisors near me".

Same machinery, new surface:
  - Queries come from ai_state_audit.category_local_prompts(business) -- ONE source of
    truth, so the AI audit, the competitor benchmark, and this local-rank tracker all
    measure the SAME local-category questions.
  - Results come from Serper's Google SERP (organic + the 'places' local pack),
    GEO-TARGETED by the business's service area, so the rank reflects what a LOCAL
    searcher sees -- not a generic national result.
  - We record OUR rank AND each registered competitor's, so the console can show
    "page 1 or not", movement over time, and who out-ranks us locally.

This is the lead-gen complement to reputation: drowning out the bad stuff in AI answers
AND climbing the local Google results that drive walk-in / call-in business.

Honesty + safety:
  - Ranks are a transparent read of the live SERP at capture time; SERPs personalize and
    drift, so a single capture is a snapshot, not a guarantee (flagged in the payload).
  - Activates only when SERPER_API_KEY is set. With no key, track() records NOTHING --
    we never fabricate ranks.
  - A failed/empty SERP call is recorded as "not found" only when the call SUCCEEDED but
    the party was absent; a FAILED call is skipped (not counted as absence).

Run:
    python -m rep_engine.local_seo track   --business-id 1
    python -m rep_engine.local_seo show    --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

try:
    from .db import db
    from . import http as _http
    from .textutils import strip_www as _strip_www
    from . import ai_state_audit as _audit
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import http as _http  # type: ignore
    from textutils import strip_www as _strip_www  # type: ignore
    import ai_state_audit as _audit  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("local_seo")

SERPER_BASE = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")
# how many organic results to scan for our domain (page 1 = top 10; we scan 2 pages
# so we can also report "ranking but on page 2" rather than a bare "not found").
ORGANIC_SCAN = 20


def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS local_rankings (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            run_id BIGINT,
            query TEXT,
            location TEXT,
            party TEXT,                     -- 'subject' or the competitor's name
            is_subject BOOLEAN DEFAULT FALSE,
            organic_rank INT,               -- 1..N, NULL when not found in scanned results
            local_pack_rank INT,            -- 1..k, NULL when not in the local/map pack
            on_page_one BOOLEAN DEFAULT FALSE,
            url TEXT DEFAULT '',
            title TEXT DEFAULT '',
            found BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT now())""")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_local_rankings_biz "
            "ON local_rankings(business_id, run_id DESC, id)")
        conn.commit()


def _host(url: str) -> str:
    try:
        net = urlparse(url if "//" in url else "//" + url).netloc or url
        return _strip_www(net.split("@")[-1].split(":")[0].lower())
    except Exception:  # pragma: no cover -- never let a malformed URL break a run
        return ""


def _serper_local(query: str, location: str, num: int = ORGANIC_SCAN) -> Optional[dict]:
    """Geo-targeted Google SERP via Serper. Returns the full response dict (organic +
    'places'), or None when SERPER_API_KEY is unset or the call failed. The `location`
    string (e.g. 'Cincinnati, Ohio, United States') is what makes the rank LOCAL."""
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return None
    body = {"q": query, "num": num, "gl": "us"}
    if location:
        body["location"] = location
    res = _http.request_json(
        "POST", f"{SERPER_BASE}/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json=body, timeout=20, max_retries=2,
    )
    if res.failed or not isinstance(res.data, dict):
        return None
    return res.data


# Generic category/firm words that are NOT distinctive enough to match a party by title.
# Without this, a domain-less competitor named for the category (e.g. "Ace Financial")
# would match EVERY category-local result title ("Best financial services in ..."), since
# those titles all contain the category word. The business's own service words are added
# to this set per-run (see _category_stop).
_GENERIC_NAME_WORDS = {
    "financial", "finance", "services", "service", "insurance", "insurances", "advisor",
    "advisors", "advisory", "group", "company", "companies", "associates", "partners",
    "wealth", "management", "planning", "solutions", "agency", "agencies", "consulting",
    "consultants", "firm", "the", "and", "llc", "inc", "corp", "co", "near",
}


def _category_stop(biz: dict) -> set[str]:
    """Per-run stop-words: the generic firm words plus the business's own service/category
    words, so neither side is matched against a result purely on a shared category noun."""
    import re
    svc = {w for w in re.split(r"\W+", (biz.get("services") or "").lower()) if len(w) >= 4}
    return _GENERIC_NAME_WORDS | svc


def _name_tokens(name: str, stop: Optional[set] = None) -> list[str]:
    """Distinctive (>=4-char) tokens of a party name, with generic category/firm words
    removed -- so title matching keys on what's actually unique to the party."""
    import re
    stop = stop or _GENERIC_NAME_WORDS
    return [t for t in re.split(r"\W+", (name or "").lower())
            if len(t) >= 4 and t not in stop]


def _raw_tokens(name: str) -> list[str]:
    import re
    return [t for t in re.split(r"\W+", (name or "").lower()) if len(t) >= 2]


def _match_party(name: str, domain: str, *, title: str, link: str,
                 stop: Optional[set] = None) -> bool:
    """Does this SERP entry belong to the party? Domain match (host equality, or the
    result host being a subdomain of the party domain) first, then a name-token match on
    the title that requires ALL distinctive tokens -- never a lone category word."""
    dom = _strip_www((domain or "").lower())
    host = _host(link)
    # host == party domain, or the result host is a SUBDOMAIN of the party domain.
    # (We do NOT match the reverse -- a party domain being a subdomain of the result host --
    # because that credits bare shared-hosting providers, e.g. *.wordpress.com.)
    if dom and host and (host == dom or host.endswith("." + dom)):
        return True
    t = (title or "").lower()
    toks = _name_tokens(name, stop)
    if toks:
        return all(tok in t for tok in toks)           # all distinctive tokens present
    # name collapsed to only generic/short words -> require the FULL token set so a generic
    # category word alone can't match (and an all-short name still needs every token).
    raw = _raw_tokens(name)
    return bool(raw) and all(tok in t for tok in raw)


def _as_rank(val, fallback: int) -> int:
    """SERP 'position' coerced to a positive int; falls back to the 1-based index when the
    field is missing or non-numeric, so one malformed result can't abort the whole run."""
    try:
        n = int(val)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _rank_in_organic(organic: list, name: str, domain: str,
                     stop: Optional[set] = None) -> tuple[Optional[int], str, str]:
    """First organic position whose link/title matches the party. Position is taken from
    the result's own 'position' field when present, else its 1-based index."""
    for i, r in enumerate(organic or [], start=1):
        link = r.get("link") or ""
        title = r.get("title") or ""
        if _match_party(name, domain, title=title, link=link, stop=stop):
            return _as_rank(r.get("position"), i), link, title
    return None, "", ""


def _rank_in_places(places: list, name: str, domain: str,
                    stop: Optional[set] = None) -> Optional[int]:
    """Position of the party in the local 'places' (map) pack, if present."""
    for i, p in enumerate(places or [], start=1):
        title = p.get("title") or ""
        link = p.get("website") or p.get("link") or ""
        if _match_party(name, domain, title=title, link=link, stop=stop):
            return _as_rank(p.get("position"), i)
    return None


def _record(conn, business_id, run_id, query, location, party, is_subject,
            organic_rank, local_pack_rank, url, title) -> None:
    found = organic_rank is not None or local_pack_rank is not None
    on_page_one = organic_rank is not None and organic_rank <= 10
    conn.execute(
        """INSERT INTO local_rankings (business_id, run_id, query, location, party,
            is_subject, organic_rank, local_pack_rank, on_page_one, url, title, found)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (business_id, run_id, query, location, party, is_subject,
         organic_rank, local_pack_rank, on_page_one, url or "", title or "", found),
    )


def track(business_id: int, quiet: bool = False) -> dict:
    """Capture local Google rankings for the subject + each registered competitor across
    the business's category-local queries. No-op (records nothing) without SERPER_API_KEY."""
    _ensure()
    if not os.getenv("SERPER_API_KEY", ""):
        if not quiet:
            log.info("SERPER_API_KEY not set; local rank tracking is off (nothing recorded).")
        return {"skipped": True, "reason": "no SERPER_API_KEY"}

    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            # ValueError (not SystemExit) so the background-job runner records a failed job
            # instead of the SystemExit (a BaseException) escaping and tearing down the loop.
            raise ValueError(f"No business id {business_id}")
        location = (biz.get("geo") or "").strip()
        queries = _audit.category_local_prompts(dict(biz))
        if not queries:
            if not quiet:
                log.info("No service area (geo) set for business %d; no local queries to track.",
                         business_id)
            return {"skipped": True, "reason": "no geo / no local queries"}
        comps = conn.execute(
            "SELECT name, domain FROM competitors WHERE business_id=%s", (business_id,)
        ).fetchall()

        run = conn.execute("INSERT INTO audit_runs (business_id) VALUES (%s) RETURNING id",
                           (business_id,)).fetchone()
        run_id = run["id"]
        subj_name = biz["name"]
        subj_domain = biz.get("domain") or ""
        stop = _category_stop(dict(biz))   # drop the business's own category words from title matching
        recorded = 0
        for q in queries:
            data = _serper_local(q, location)
            if data is None:
                continue  # failed call -> skip (never counted as an absence)
            organic = data.get("organic", []) or []
            places = data.get("places", []) or data.get("local", []) or []
            # subject
            o_rank, url, title = _rank_in_organic(organic, subj_name, subj_domain, stop)
            p_rank = _rank_in_places(places, subj_name, subj_domain, stop)
            _record(conn, business_id, run_id, q, location, "subject", True,
                    o_rank, p_rank, url, title)
            recorded += 1
            # competitors
            for c in comps:
                co_rank, curl, ctitle = _rank_in_organic(organic, c["name"], c.get("domain") or "", stop)
                cp_rank = _rank_in_places(places, c["name"], c.get("domain") or "", stop)
                _record(conn, business_id, run_id, q, location, c["name"], False,
                        co_rank, cp_rank, curl, ctitle)
                recorded += 1
        conn.execute("UPDATE audit_runs SET finished_at=now() WHERE id=%s", (run_id,))
        conn.commit()
    if not quiet:
        log.info("Local rank run %d complete (%d rows across %d queries).",
                 run_id, recorded, len(queries))
    return {"run_id": run_id, "rows": recorded, "queries": len(queries)}


def latest(business_id: int) -> dict:
    """Latest local-rank run as a console-ready payload: per-query subject rank +
    competitor ranks, plus a roll-up (page-1 rate, local-pack rate, average position)."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            return {}
        run = conn.execute(
            "SELECT MAX(run_id) r FROM local_rankings WHERE business_id=%s", (business_id,)
        ).fetchone()
        if not run or run["r"] is None:
            return {"business": biz["name"], "run_id": None, "queries": [], "summary": None}
        rid = run["r"]
        rows = conn.execute(
            "SELECT query, location, party, is_subject, organic_rank, local_pack_rank, "
            "on_page_one, url, title, found FROM local_rankings "
            "WHERE business_id=%s AND run_id=%s ORDER BY query, is_subject DESC, organic_rank NULLS LAST",
            (business_id, rid),
        ).fetchall()

    by_query: dict[str, dict] = {}
    for r in rows:
        q = by_query.setdefault(r["query"], {"query": r["query"], "location": r["location"],
                                             "subject": None, "competitors": []})
        entry = {"name": r["party"], "organic_rank": r["organic_rank"],
                 "local_pack_rank": r["local_pack_rank"], "on_page_one": r["on_page_one"],
                 "url": r["url"], "title": r["title"], "found": r["found"]}
        if r["is_subject"]:
            q["subject"] = entry
        else:
            q["competitors"].append(entry)

    subj = [v["subject"] for v in by_query.values() if v["subject"]]
    n = len(subj) or 1
    page_one = sum(1 for s in subj if s["on_page_one"])
    in_pack = sum(1 for s in subj if s["local_pack_rank"] is not None)
    ranked = [s["organic_rank"] for s in subj if s["organic_rank"] is not None]
    summary = {
        "queries": len(subj),
        "page_one_rate": round(page_one / n, 3),
        "local_pack_rate": round(in_pack / n, 3),
        "avg_organic_rank": round(sum(ranked) / len(ranked), 1) if ranked else None,
        "ranked_queries": len(ranked),
        "note": ("Snapshot of the live Google SERP at capture time, geo-targeted to the "
                 "service area. SERPs personalize and drift, so treat a single capture as "
                 "a directional read, not a guarantee."),
    }
    return {"business": biz["name"], "run_id": rid,
            "queries": list(by_query.values()), "summary": summary}


def main() -> None:
    ap = argparse.ArgumentParser(description="Local Google rank tracking (organic + local pack)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("track"); t.add_argument("--business-id", type=int, required=True)
    s = sub.add_parser("show"); s.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "track":
        track(args.business_id)
    elif args.cmd == "show":
        print(json.dumps(latest(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
