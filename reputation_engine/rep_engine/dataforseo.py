"""
DataForSEO client — reputation & SEO intelligence beyond keyword volume
=======================================================================
Centralizes the DataForSEO calls added from the cost analysis (keyword volume itself lives in
keyword_research.py). Three capabilities, each cheap and on-mission for a reputation product:

  1. Competitor keyword intelligence  (Labs ranked_keywords / competitors_domain) ~$0.012/call
     -> what a competitor ranks for that the client doesn't = keyword GAPS -> stored as opportunities.
  2. Brand mentions + sentiment        (Content Analysis search)                  cheap
     -> where the brand is discussed across the web, with sentiment -> monitoring signal.
  3. Reviews across platforms          (Business Data google/trustpilot reviews)  $0.0008/req
     -> Google + Trustpilot review pull for ANY business (competitors too), no OAuth. Task-based
        (post -> poll -> store). TripAdvisor intentionally excluded (irrelevant to finance/services).

Everything reuses keyword_research's auth/balance/location helpers, records exact cost to the ledger,
is balance-guarded, and is fully dormant-safe (no creds -> {skipped}). Never raises.

Run:  python -m rep_engine.dataforseo competitors --business-id 1
      python -m rep_engine.dataforseo mentions --business-id 1
      python -m rep_engine.dataforseo reviews --business-id 1 --platform google
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import Optional

try:
    from .db import db
    from . import http as _http
    from . import cost as _cost
    from .keyword_research import (_dataforseo_auth, dataforseo_balance, _dfs_labs_location,
                                   _dfs_clean_kw, volume_configured)
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    import http as _http  # type: ignore
    import cost as _cost  # type: ignore
    from keyword_research import (_dataforseo_auth, dataforseo_balance, _dfs_labs_location,  # type: ignore
                                  _dfs_clean_kw, volume_configured)

log = logging.getLogger("dataforseo")
_BASE = "https://api.dataforseo.com/v3"


def configured() -> bool:
    return volume_configured() and (os.getenv("KEYWORD_VOLUME_PROVIDER", "").strip().lower() == "dataforseo")


def _guard_ok() -> bool:
    """Balance floor guard shared with keyword volume."""
    try:
        floor = float(os.getenv("DATAFORSEO_MIN_BALANCE", "0.20") or 0)
    except (TypeError, ValueError):
        floor = 0.20
    if floor <= 0:
        return True
    bal = dataforseo_balance()
    if bal is not None and bal < floor:
        log.warning("DataForSEO balance $%.2f < $%.2f floor -- skipping call. Top up to resume.", bal, floor)
        return False
    return True


def _post(endpoint: str, body: list, business_id: Optional[int], category: str, op: str,
          units: float = 1, unit_label: str = "requests", timeout: int = 60) -> Optional[dict]:
    """POST to a DataForSEO endpoint, record the EXACT cost it returns, return the parsed data."""
    if not configured() or not _guard_ok():
        return None
    res = _http.request_json("POST", f"{_BASE}/{endpoint}",
                             headers={"Authorization": f"Basic {_dataforseo_auth()}", "Content-Type": "application/json"},
                             json=body, timeout=timeout, max_retries=2, guard_redirects=True)
    if not (res.ok and isinstance(res.data, dict)):
        log.warning("dataforseo %s failed: %s", endpoint, getattr(res, "error", None) or getattr(res, "status", "?"))
        return None
    try:
        exact = res.data.get("cost")
        _cost.record_cost(business_id, None, category, "dataforseo", op,
                          cost_usd=float(exact) if exact not in (None, 0) else None,
                          units=units, unit_label=unit_label,
                          detail={"endpoint": endpoint, "exact_cost": exact, "status": res.data.get("status_message")})
    except Exception:  # noqa: BLE001
        pass
    return res.data


def _biz(business_id: int) -> dict:
    with db() as conn:
        r = conn.execute("SELECT name, domain, geo, services, industry FROM businesses WHERE id=%s",
                         (business_id,)).fetchone()
    return dict(r) if r else {}


import re as _re
# Over-generic words that shouldn't, on their own, make a competitor keyword "relevant" to the client.
# (Service anchors like 'insurance'/'financial'/'retirement' are DELIBERATELY not here — sharing one
# of those with the client's vocabulary is exactly the relevance signal we want.)
_REL_STOP = {"and", "the", "for", "your", "our", "with", "near", "best", "top", "how", "what", "why",
             "who", "does", "get", "are", "you", "can", "will", "from", "that", "this", "com", "www",
             "cincinnati", "ohio", "company", "companies", "services", "service"}


def _rel_tokens(s: str) -> set:
    return {w for w in _re.findall(r"[a-z]{4,}", (s or "").lower()) if w not in _REL_STOP}


# ---------------------------------------------------------------------------
# 1. Competitor keyword intelligence
# ---------------------------------------------------------------------------
def _clean_domain(d: str) -> str:
    d = (d or "").strip().lower()
    for p in ("https://", "http://", "www."):
        if d.startswith(p):
            d = d[len(p):]
    return d.split("/")[0].strip()


def ranked_keywords(domain: str, business_id: Optional[int] = None, geo: str = "", limit: int = 100) -> list[dict]:
    """Keywords a domain ranks for (organic), with volume + position. ~$0.012/call."""
    dom = _clean_domain(domain)
    if not dom:
        return []
    body = [{"target": dom, "location_name": _dfs_labs_location(geo), "language_name": "English",
             "limit": max(1, min(1000, limit)), "order_by": ["keyword_data.keyword_info.search_volume,desc"]}]
    data = _post("dataforseo_labs/google/ranked_keywords/live", body, business_id,
                 "competitor_intel", "labs/ranked_keywords")
    out: list[dict] = []
    if not data:
        return out
    for task in data.get("tasks") or []:
        for result in (task.get("result") or []):
            for it in (result.get("items") or []):
                kd = it.get("keyword_data") or {}
                ki = kd.get("keyword_info") or {}
                se = (it.get("ranked_serp_element") or {}).get("serp_item") or {}
                out.append({"keyword": kd.get("keyword"), "search_volume": ki.get("search_volume"),
                            "cpc": ki.get("cpc"), "rank": se.get("rank_absolute")})
    return out


def keyword_gaps(business_id: int, per_competitor: int = 100) -> dict:
    """For each of the client's competitors, pull what THEY rank for and surface the keywords the
    client isn't already targeting = keyword GAPS. Stores the best gaps into target_keywords with
    source='competitor_gap' so they flow into keyword-driven content programs. Fail-safe."""
    if not configured():
        return {"skipped": True, "reason": "DataForSEO not configured"}
    biz = _biz(business_id)
    geo = biz.get("geo") or ""
    with db() as conn:
        comps = conn.execute("SELECT name, domain FROM competitors WHERE business_id=%s AND domain IS NOT NULL "
                             "AND domain <> ''", (business_id,)).fetchall()
        have = {(_r["keyword"] or "").strip().lower() for _r in
                conn.execute("SELECT keyword FROM target_keywords WHERE business_id=%s", (business_id,)).fetchall()}
    if not comps:
        return {"skipped": True, "reason": "no competitors with a domain set"}
    # RELEVANCE: a competitor ranks for thousands of keywords, most irrelevant to the client (their
    # brand name, generic finance terms like 'stock market', calculators). Keep only keywords that
    # (a) share a meaningful token with the client's services/existing keyword vocabulary, and
    # (b) don't contain a competitor's brand name. This is what turns raw ranked_keywords into real,
    # on-topic opportunities instead of noise.
    relevant = _rel_tokens((biz.get("services") or "") + " " + (biz.get("industry") or ""))
    with db() as conn:
        for kwr in conn.execute("SELECT keyword FROM target_keywords WHERE business_id=%s", (business_id,)).fetchall():
            relevant |= _rel_tokens(kwr["keyword"])
    brand_toks: set = set()
    for c in comps:
        brand_toks |= _rel_tokens(c["name"]) | _rel_tokens(_clean_domain(c["domain"]).split(".")[0])
    relevant -= brand_toks   # a token that's also a competitor brand word isn't a relevance anchor

    def _relevant(kw: str) -> bool:
        kt = _rel_tokens(kw)
        if not kt or (kt & brand_toks):     # empty or contains a competitor brand word
            return False
        return bool(kt & relevant)          # shares a client service/keyword token

    gaps: dict = {}
    for c in comps:
        for r in ranked_keywords(c["domain"], business_id, geo, per_competitor):
            kw = (r.get("keyword") or "").strip()
            if not kw or kw.lower() in have or (r.get("search_volume") or 0) < 10:
                continue
            if not _relevant(kw):
                continue
            g = gaps.get(kw.lower())
            if not g or (r.get("search_volume") or 0) > (g.get("search_volume") or 0):
                gaps[kw.lower()] = {"keyword": kw, "search_volume": r.get("search_volume"),
                                    "cpc": r.get("cpc"), "competitor": c["name"]}
    # store the top gaps by volume as opportunities
    ranked = sorted(gaps.values(), key=lambda x: (x.get("search_volume") or 0), reverse=True)[:40]
    stored = 0
    with db() as conn:
        for g in ranked:
            try:
                stored += conn.execute(
                    "INSERT INTO target_keywords (business_id, keyword, kind, source, intent, priority, "
                    "rationale, search_volume, cpc) VALUES (%s,%s,'competitor_gap','dataforseo_competitor', "
                    "NULL, 40, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (business_id, g["keyword"], f"Competitor {g['competitor']} ranks for this; you don't.",
                     g.get("search_volume"), g.get("cpc"))).rowcount
            except Exception as e:  # noqa: BLE001 -- one bad row must not abort
                log.debug("keyword_gap insert skipped: %s", e)
        conn.commit()
    return {"competitors": len(comps), "gaps_found": len(gaps), "stored": stored,
            "top_gaps": ranked[:10]}


# ---------------------------------------------------------------------------
# 2. Brand mentions + sentiment (Content Analysis)
# ---------------------------------------------------------------------------
def mentions(business_id: int, keyword: Optional[str] = None) -> dict:
    """Where the brand is mentioned across the web + overall sentiment (Content Analysis). Fail-safe."""
    if not configured():
        return {"skipped": True, "reason": "DataForSEO not configured"}
    kw = (keyword or _biz(business_id).get("name") or "").strip()
    if not kw:
        return {"skipped": True, "reason": "no brand keyword"}
    body = [{"keyword": kw, "page_type": ["ecommerce", "news", "blogs", "message-boards", "organic"],
             "internal_list_limit": 20, "positive_connotation_threshold": 0.4}]
    data = _post("content_analysis/search/live", body, business_id, "mentions", "content_analysis/search")
    if not data:
        return {"skipped": True, "reason": "no result (check DataForSEO Content Analysis access)"}
    res = ((data.get("tasks") or [{}])[0].get("result") or [{}])[0]
    items = res.get("items") or []
    return {"keyword": kw, "total_count": res.get("total_count"),
            "sentiment": res.get("sentiment_connotations") or res.get("rating") or {},
            "sample": [{"url": (i.get("url") or ""), "title": i.get("main_title"),
                        "sentiment": (i.get("sentiment_connotations") or {})} for i in items[:10]]}


# ---------------------------------------------------------------------------
# 3. Reviews across platforms (Google + Trustpilot) -- task-based (async)
# ---------------------------------------------------------------------------
_REVIEW_ENDPOINTS = {
    "google": "business_data/google/reviews",
    "trustpilot": "business_data/trustpilot/reviews",
}


def get_reviews(business_id: int, platform: str = "google", term: Optional[str] = None,
                depth: int = 50, poll_secs: int = 90) -> dict:
    """Fetch reviews for a business from Google or Trustpilot. Posts the task, polls until ready (up to
    poll_secs), and returns the reviews + rating summary. Returns {pending} if not ready in time (a
    later run retrieves via the same task). Fail-safe + balance-guarded. $0.0008/request."""
    if not configured():
        return {"skipped": True, "reason": "DataForSEO not configured"}
    ep = _REVIEW_ENDPOINTS.get(platform)
    if not ep:
        return {"skipped": True, "reason": f"unsupported platform '{platform}'"}
    biz = _biz(business_id)
    kw = (term or biz.get("name") or "").strip()
    if not kw:
        return {"skipped": True, "reason": "no business name/term to look up"}
    post_body = [{"keyword": kw, "depth": max(10, min(700, depth)),
                  "location_name": "United States", "language_name": "English"}]
    posted = _post(f"{ep}/task_post", post_body, business_id, "reviews", f"{platform}/reviews.post")
    if not posted:
        return {"skipped": True, "reason": "task_post failed"}
    task = (posted.get("tasks") or [{}])[0]
    task_id = task.get("id")
    if not task_id:
        return {"skipped": True, "reason": "no task id", "status": task.get("status_message")}
    # poll until ready (retrieval is free)
    deadline = time.monotonic() + max(10, poll_secs)
    while time.monotonic() < deadline:
        ready = _http.request_json("GET", f"{_BASE}/{ep}/tasks_ready",
                                   headers={"Authorization": f"Basic {_dataforseo_auth()}"},
                                   timeout=20, max_retries=1, guard_redirects=True)
        ids = []
        if ready.ok and isinstance(ready.data, dict):
            for t in ready.data.get("tasks") or []:
                for r in (t.get("result") or []):
                    if r.get("id"):
                        ids.append(r["id"])
        if task_id in ids:
            break
        time.sleep(6)
    got = _http.request_json("GET", f"{_BASE}/{ep}/task_get/{task_id}",
                             headers={"Authorization": f"Basic {_dataforseo_auth()}"},
                             timeout=30, max_retries=1, guard_redirects=True)
    if not (got.ok and isinstance(got.data, dict)):
        return {"pending": True, "task_id": task_id, "reason": "not ready yet — retrieve later"}
    result = ((got.data.get("tasks") or [{}])[0].get("result") or [{}])[0]
    items = result.get("items") or []
    revs = [{"rating": (i.get("rating") or {}).get("value"), "text": i.get("review_text"),
             "author": i.get("profile_name"), "date": i.get("timestamp")} for i in items if i.get("review_text")]
    return {"platform": platform, "business": kw, "rating": result.get("rating"),
            "reviews_count": result.get("reviews_count"), "reviews": revs[:depth]}


# ---------------------------------------------------------------------------
# job entry points
# ---------------------------------------------------------------------------
def run_intel(business_id: int) -> dict:
    """One cheap synchronous pass: competitor keyword gaps + brand mentions/sentiment."""
    return {"keyword_gaps": keyword_gaps(business_id), "mentions": mentions(business_id)}


def run_reviews(business_id: int) -> dict:
    """Pull Google (+ Trustpilot if enabled) reviews. Trustpilot is opt-in via DATAFORSEO_TRUSTPILOT=1
    since many local/service businesses aren't listed there."""
    out = {"google": get_reviews(business_id, "google")}
    if (os.getenv("DATAFORSEO_TRUSTPILOT", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
        out["trustpilot"] = get_reviews(business_id, "trustpilot")
    return out


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser(description="DataForSEO intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("competitors", "mentions", "intel", "reviews"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
        if c == "reviews":
            p.add_argument("--platform", default="google")
    args = ap.parse_args()
    if args.cmd == "competitors":
        out = keyword_gaps(args.business_id)
    elif args.cmd == "mentions":
        out = mentions(args.business_id)
    elif args.cmd == "reviews":
        out = get_reviews(args.business_id, args.platform)
    else:
        out = run_intel(args.business_id)
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
