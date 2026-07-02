"""
Reputation Crowding-Out Engine -- Keyword Intelligence (CI-1)
============================================================
Identifies the SEO keywords a business must include in its website, blog, social,
and Google Business Profile to rank locally -- so content generation, the gap model,
and local-SEO recommendations all target the RIGHT language instead of guessing.

Two grounded sources, combined:
  1. LLM SEED   -- an LLM proposes candidate terms from the business profile + the
                   crawled site (entities it's missing) + competitor names. Breadth + intent.
  2. SERPER GROUND -- real Google data via the Serper key we already pay for:
                   relatedSearches, peopleAlsoAsk (question keywords), and /autocomplete.
                   This is what actual searchers type, not the model's guess.

Output: a ranked `target_keywords` set per business (primary / secondary / long_tail /
local / question), stored for the content generator (`_grounding_context` reads it),
the gap model, and a "Keywords to rank for" view. True search VOLUME needs a paid
keyword API (DataForSEO / Keywords Everywhere) -- a later enrichment, not required here.

Run:
    python -m rep_engine.keyword_research research --business-id 2
    python -m rep_engine.keyword_research show     --business-id 2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Optional

try:
    from .db import db
    from . import http as _http
    from . import ai_state_audit as _llm
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import http as _http  # type: ignore
    import ai_state_audit as _llm  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("keyword_research")

SERPER_BASE = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")

# Priority by kind (higher = more important to rank for). Local + primary lead because this
# is a local lead-gen business; question keywords feed FAQ/AEO content AI loves to cite.
_KIND_PRIORITY = {"primary": 100, "local": 90, "question": 70, "secondary": 60, "long_tail": 40}
_MAX_SEEDS_TO_EXPAND = 6     # bound Serper spend
_MAX_STORED = 45             # keep the set focused


def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS target_keywords (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            kind TEXT,            -- primary|secondary|long_tail|local|question
            source TEXT,          -- llm_seed|serper_related|serper_paa|serper_autocomplete
            intent TEXT,          -- informational|commercial|local|navigational
            priority INT,
            rationale TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, keyword))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_target_keywords_biz "
                     "ON target_keywords(business_id, priority DESC)")
        # CI-5 volume columns (fresh-DB parity with migration 0054)
        for ddl in (
            "ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS search_volume INT",
            "ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS keyword_difficulty INT",
            "ALTER TABLE target_keywords ADD COLUMN IF NOT EXISTS cpc NUMERIC(8,2)",
        ):
            conn.execute(ddl)
        conn.commit()


# ---------------------------------------------------------------------------
# CI-5: optional search-volume enrichment (dormant until a provider key is set)
# ---------------------------------------------------------------------------
def volume_configured() -> bool:
    prov = (os.getenv("KEYWORD_VOLUME_PROVIDER") or "").strip().lower()
    if prov == "dataforseo":
        return bool(os.getenv("DATAFORSEO_LOGIN") and os.getenv("DATAFORSEO_PASSWORD"))
    if prov == "keywords_everywhere":
        return bool(os.getenv("KEYWORDS_EVERYWHERE_API_KEY"))
    return False


def _enrich_volume(keywords: list[str], location: str) -> dict:
    """Return {keyword_lower: {search_volume, keyword_difficulty, cpc}} from the configured provider.
    Dormant-safe: returns {} when no provider key is set or the call fails."""
    if not volume_configured() or not keywords:
        return {}
    prov = (os.getenv("KEYWORD_VOLUME_PROVIDER") or "").strip().lower()
    try:
        if prov == "dataforseo":
            return _dataforseo_volume(keywords, location)
        if prov == "keywords_everywhere":
            return _keywords_everywhere_volume(keywords)
    except Exception as e:  # noqa: BLE001 -- enrichment is best-effort
        log.debug("volume enrichment failed: %s", e)
    return {}


def _dataforseo_volume(keywords: list[str], location: str) -> dict:
    import base64 as _b64
    login = os.getenv("DATAFORSEO_LOGIN", "")
    pw = os.getenv("DATAFORSEO_PASSWORD", "")
    auth = _b64.b64encode(f"{login}:{pw}".encode()).decode("ascii")
    body = [{"keywords": [k[:80] for k in keywords[:700]],
             "location_name": location or "United States", "language_name": "English"}]
    res = _http.request_json(
        "POST", "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json=body, timeout=60, max_retries=2, guard_redirects=True)
    out: dict = {}
    if res.ok and isinstance(res.data, dict):
        for task in res.data.get("tasks") or []:
            for item in (task.get("result") or []):
                kw = (item.get("keyword") or "").lower()
                if kw:
                    comp = item.get("competition_index")
                    out[kw] = {"search_volume": item.get("search_volume"),
                               "keyword_difficulty": int(comp) if isinstance(comp, (int, float)) else None,
                               "cpc": item.get("cpc")}
    return out


def _keywords_everywhere_volume(keywords: list[str]) -> dict:
    key = os.getenv("KEYWORDS_EVERYWHERE_API_KEY", "")
    res = _http.request_json(
        "POST", "https://api.keywordseverywhere.com/v1/get_keyword_data",
        headers={"Authorization": f"Bearer {key}"},
        data={"dataSource": "gkp", "country": "us", "currency": "usd",
              "kw[]": [k[:80] for k in keywords[:100]]},
        timeout=60, max_retries=2, guard_redirects=True)
    out: dict = {}
    if res.ok and isinstance(res.data, dict):
        for item in res.data.get("data") or []:
            kw = (item.get("keyword") or "").lower()
            if kw:
                out[kw] = {"search_volume": item.get("vol"), "keyword_difficulty": item.get("competition"),
                           "cpc": (item.get("cpc") or {}).get("value")}
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------------------
# Off-brand / off-topic filtering
# ---------------------------------------------------------------------------
# Serper's relatedSearches / peopleAlsoAsk / autocomplete happily return queries about OTHER
# companies (competitor brands) and job-seeker "is <company> a good place to work" questions.
# Those are NOT keywords THIS business should target or build topic authority around, so we drop
# them before storing. (Reported: "Is Cincinnati Financial a good place to work?" / "Cincinnati
# Insurance" showing up as topic authorities for a business that is neither of those companies.)
_EMPLOYER_RE = re.compile(
    r"\b(good place to work|great place to work|good company to work|work(?:ing)? (?:at|for)|"
    r"careers?|hiring|glassdoor|indeed|employee reviews?|salary|salaries|benefits package|"
    r"who owns|headquarters|stock price|ceo of)\b",
    re.I,
)


def _name_tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def _blocked_phrases(ctx: dict) -> list[str]:
    """Full brand phrases (competitors + confusion/contested entities) that a candidate keyword
    naming a DIFFERENT company would contain. Whole-phrase (>=5 chars) so we never drop a keyword
    just for sharing the client's own city/word."""
    phrases: list[str] = []
    ct = ctx.get("contested_terms")
    if isinstance(ct, str):
        ct = [t for t in re.split(r"[,\n;]+", ct) if t.strip()]
    for src in (ctx.get("competitors") or []), (ct or []):
        for name in src:
            p = _norm(name)
            if len(p) >= 5:
                phrases.append(p)
    return phrases


def _is_offtopic(keyword: str, blocked: list[str], client_tokens: set[str]) -> bool:
    n = _norm(keyword)
    if not n:
        return True
    # names another company (a competitor or a confusion entity)
    for b in blocked:
        if b and b in n:
            return True
    # employer-reputation / job-seeker / corporate-profile query about someone OTHER than the client
    if _EMPLOYER_RE.search(n) and not (client_tokens & _name_tokens(n)):
        return True
    return False


_RELEVANCE_SYSTEM = (
    "You audit candidate SEO keywords for ONE specific business. Return STRICT JSON "
    "{\"drop\":[str,...]} listing the EXACT candidate strings to REMOVE because they are not "
    "relevant to THIS business: keywords that name a DIFFERENT company or brand (competitors or "
    "unrelated organizations), employer-reputation or job-seeker queries about other companies "
    "(e.g. 'is <other company> a good place to work', 'careers', 'glassdoor', 'salary'), or terms "
    "off-topic for this business's services and customers. KEEP everything a prospective CUSTOMER "
    "of this business would plausibly search (its services, category, questions, and location). "
    "If nothing should be removed, return {\"drop\":[]}."
)


def _drop_offbrand_llm(candidates: list[dict], ctx: dict) -> set[str]:
    """LLM relevance safety net: returns the normalized keywords to drop. Fail-safe — on any error
    or unparseable response it drops nothing (never nukes the whole set)."""
    if not candidates:
        return set()
    payload = json.dumps({
        "business": {k: ctx.get(k) for k in ("name", "industry", "services", "geo")},
        "competitors": ctx.get("competitors"),
        "candidates": [c["keyword"] for c in candidates],
    })[:8000]
    try:
        res = _llm.orchestrator_json(_RELEVANCE_SYSTEM, payload, tier="mid")
    except Exception as e:  # noqa: BLE001 -- relevance filtering is best-effort
        log.debug("relevance filter failed: %s", e)
        return set()
    drop = (res or {}).get("drop") if isinstance(res, dict) else None
    return {_norm(d) for d in (drop or []) if isinstance(d, str) and d.strip()}


# ---------------------------------------------------------------------------
# Serper grounding (real Google data)
# ---------------------------------------------------------------------------
def _serper(endpoint: str, body: dict) -> Optional[dict]:
    # Shared TTL cache (Phase E): keyword research reuses autocomplete/PAA/related queries that the
    # audit + local-rank also issue -- cache collapses the duplicate paid calls.
    try:
        from . import serper as _sc
    except ImportError:  # pragma: no cover
        import serper as _sc  # type: ignore
    return _sc.cached_post(endpoint, body)


def _expand_with_serper(seed: str, location: str) -> list[dict]:
    """relatedSearches + peopleAlsoAsk + autocomplete for one seed -> classified candidates."""
    out: list[dict] = []
    body = {"q": seed, "gl": "us"}
    if location:
        body["location"] = location
    data = _serper("search", body)
    if data:
        for r in (data.get("relatedSearches") or [])[:10]:
            q = r.get("query") if isinstance(r, dict) else r
            if q:
                out.append({"keyword": q, "kind": "long_tail", "source": "serper_related", "intent": "commercial"})
        for r in (data.get("peopleAlsoAsk") or [])[:8]:
            q = r.get("question") if isinstance(r, dict) else r
            if q:
                out.append({"keyword": q, "kind": "question", "source": "serper_paa", "intent": "informational"})
    ac = _serper("autocomplete", {"q": seed, "gl": "us"})
    if ac:
        for r in (ac.get("suggestions") or [])[:8]:
            q = r.get("value") if isinstance(r, dict) else r
            if q:
                out.append({"keyword": q, "kind": "long_tail", "source": "serper_autocomplete", "intent": "commercial"})
    return out


# ---------------------------------------------------------------------------
# LLM seeding (breadth + intent, grounded in profile + site + competitors)
# ---------------------------------------------------------------------------
_SEED_SYSTEM = (
    "You are a local-SEO keyword strategist. Given a business profile, what its own website "
    "already covers (and is MISSING), and its competitors, propose the SEO keywords it should "
    "target to rank on Google locally AND to be understood/cited by AI assistants. Return STRICT "
    "JSON only: {\"keywords\":[{\"keyword\":str,\"kind\":\"primary|secondary|local|question\","
    "\"intent\":\"commercial|informational|local|navigational\",\"rationale\":str}]}. Include: "
    "2-4 primary service terms; several local terms (service + city, 'near me'); and 4-8 question "
    "keywords real customers ask (what they'd type or ask an AI). Keep them realistic and specific "
    "to this business + its area. Do NOT include competitor or other companies' brand names, and do "
    "NOT include employer-reputation / job-seeker queries (e.g. 'is <company> a good place to work', "
    "'careers', 'glassdoor', 'salary') — only terms a prospective CUSTOMER of THIS business would "
    "search. 10-18 keywords."
)


def _seed_llm(ctx: dict) -> list[dict]:
    payload = json.dumps(ctx)[:6000]
    res = _llm.orchestrator_json(_SEED_SYSTEM, payload, tier="mid")
    items = (res or {}).get("keywords") if isinstance(res, dict) else None
    out = []
    for it in (items or []):
        kw = (it.get("keyword") or "").strip() if isinstance(it, dict) else ""
        if not kw:
            continue
        out.append({
            "keyword": kw,
            "kind": (it.get("kind") or "secondary"),
            "source": "llm_seed",
            "intent": (it.get("intent") or "commercial"),
            "rationale": (it.get("rationale") or "")[:240],
        })
    return out


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------
def _load_context(business_id: int) -> dict:
    with db() as conn:
        b = conn.execute(
            "SELECT name, industry, services, geo, goal, contested_terms FROM businesses WHERE id=%s",
            (business_id,)).fetchone()
        sa = conn.execute(
            "SELECT summary FROM site_audits WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
        comps = conn.execute(
            "SELECT name FROM competitors WHERE business_id=%s LIMIT 8", (business_id,)).fetchall()
    if not b:
        return {}
    missing: list = []
    if sa and sa["summary"]:
        s = sa["summary"] if isinstance(sa["summary"], dict) else {}
        # surface what the crawl says the site is MISSING (great keyword seeds)
        try:
            for p in (s.get("pages") or []):
                ec = ((p.get("semantic") or {}).get("entity_coverage") or {})
                missing += ec.get("missing") or []
        except Exception:  # noqa: BLE001
            pass
    return {
        "name": b["name"], "industry": b.get("industry"), "services": b.get("services"),
        "geo": b.get("geo"), "goal": b.get("goal"), "contested_terms": b.get("contested_terms"),
        "site_missing_topics": sorted(set(missing))[:12],
        "competitors": [c["name"] for c in comps],
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def research(business_id: int) -> dict:
    """LLM-seed -> Serper-ground -> rank -> store the target keyword set for a business."""
    _ensure()
    ctx = _load_context(business_id)
    if not ctx:
        return {"skipped": True, "reason": "no business"}
    seeds = _seed_llm(ctx)
    location = (ctx.get("geo") or "").strip()

    # Expand the strongest seeds (primary + local) with real Google data.
    candidates: dict[str, dict] = {}
    def _add(item: dict):
        k = _norm(item.get("keyword", ""))
        if not k or len(k) < 3:
            return
        cur = candidates.get(k)
        if cur is None or _KIND_PRIORITY.get(item.get("kind", ""), 0) > _KIND_PRIORITY.get(cur.get("kind", ""), 0):
            candidates[k] = item

    for s in seeds:
        _add(s)
    expand_for = [s for s in seeds if s.get("kind") in ("primary", "local")][:_MAX_SEEDS_TO_EXPAND]
    expanded_n = 0
    for s in expand_for:
        for e in _expand_with_serper(s["keyword"], location):
            _add(e)
            expanded_n += 1

    # Drop off-brand / off-topic candidates (competitor brands, employer-reputation queries about
    # OTHER companies) that Serper expansion drags in — they are not this business's keywords.
    blocked = _blocked_phrases(ctx)
    client_tokens = _name_tokens(ctx.get("name") or "")
    kept = {k: v for k, v in candidates.items() if not _is_offtopic(v["keyword"], blocked, client_tokens)}
    dropped_det = len(candidates) - len(kept)
    # LLM relevance safety net (fail-safe: only removes what it explicitly names; never empties the set).
    drop_norm = _drop_offbrand_llm(list(kept.values()), ctx)
    if drop_norm:
        after = {k: v for k, v in kept.items() if k not in drop_norm}
        if after:
            kept = after
    candidates = kept

    # Rank + cap.
    ranked = sorted(candidates.values(),
                    key=lambda x: _KIND_PRIORITY.get(x.get("kind", ""), 0), reverse=True)[:_MAX_STORED]

    # CI-5: enrich with real search volume / difficulty when a provider key is set (dormant otherwise).
    vol = _enrich_volume([it["keyword"] for it in ranked], location)

    with db() as conn:
        # refresh the set (a re-run reflects the latest crawl/competitors)
        conn.execute("DELETE FROM target_keywords WHERE business_id=%s", (business_id,))
        for it in ranked:
            v = vol.get(it["keyword"].lower(), {})
            conn.execute(
                "INSERT INTO target_keywords (business_id, keyword, kind, source, intent, priority, "
                "rationale, search_volume, keyword_difficulty, cpc) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (business_id, keyword) DO UPDATE SET "
                "kind=EXCLUDED.kind, source=EXCLUDED.source, intent=EXCLUDED.intent, "
                "priority=EXCLUDED.priority, search_volume=EXCLUDED.search_volume, "
                "keyword_difficulty=EXCLUDED.keyword_difficulty, cpc=EXCLUDED.cpc",
                (business_id, it["keyword"][:200], it.get("kind"), it.get("source"),
                 it.get("intent"), _KIND_PRIORITY.get(it.get("kind", ""), 50), it.get("rationale"),
                 v.get("search_volume"), v.get("keyword_difficulty"), v.get("cpc")),
            )
        conn.commit()
    out = {"seeds": len(seeds), "serper_candidates": expanded_n, "stored": len(ranked),
           "dropped_offbrand": dropped_det, "dropped_llm": len(drop_norm),
           "serper_used": bool(os.getenv("SERPER_API_KEY")), "volume_enriched": len(vol)}
    log.info("keyword research biz %d: %s", business_id, out)
    return out


def latest(business_id: int) -> list[dict]:
    """The stored target keywords for a business, highest priority first (for the UI/report)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT keyword, kind, source, intent, priority, rationale, search_volume, "
            "keyword_difficulty, cpc FROM target_keywords "
            "WHERE business_id=%s ORDER BY priority DESC NULLS LAST, keyword", (business_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("cpc") is not None:
            d["cpc"] = float(d["cpc"])
        out.append(d)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Keyword intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("research", "show"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "research":
        print(json.dumps(research(args.business_id), indent=2))
    else:
        print(json.dumps(latest(args.business_id), indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
