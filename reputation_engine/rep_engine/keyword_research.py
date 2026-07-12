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

# Priority by kind (higher = more important to rank for). reputation_defense leads: for a
# business whose #1 problem is a negative narrative ("is <business> a scam / pyramid scheme"),
# owning its own branded legitimacy queries IS the SEO job. Local + primary follow because this
# is a local lead-gen business; question keywords feed FAQ/AEO content AI loves to cite.
_KIND_PRIORITY = {"reputation_defense": 110, "primary": 100, "local": 90, "question": 70,
                  "secondary": 60, "long_tail": 40}
_VALID_KINDS = frozenset(_KIND_PRIORITY)
# Cap the long_tail share so Serper's relatedSearches/autocomplete (which classify as long_tail)
# can't crowd out primary/local/question/reputation_defense terms in the stored set.
_MAX_LONG_TAIL = 10
_MAX_SEEDS_TO_EXPAND = 6     # bound Serper spend
_MAX_STORED = 45             # keep the set focused


def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS target_keywords (
            id BIGSERIAL PRIMARY KEY,
            business_id BIGINT REFERENCES businesses(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            kind TEXT,            -- reputation_defense|primary|secondary|long_tail|local|question
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


def _enrich_volume(keywords: list[str], location: str, business_id: Optional[int] = None) -> dict:
    """Return {keyword_lower: {search_volume, keyword_difficulty, cpc}} from the configured provider.
    Dormant-safe: returns {} when no provider key is set or the call fails."""
    if not volume_configured() or not keywords:
        return {}
    prov = (os.getenv("KEYWORD_VOLUME_PROVIDER") or "").strip().lower()
    try:
        if prov == "dataforseo":
            return _dataforseo_volume(keywords, location, business_id)
        if prov == "keywords_everywhere":
            return _keywords_everywhere_volume(keywords)
    except Exception as e:  # noqa: BLE001 -- enrichment is best-effort
        log.debug("volume enrichment failed: %s", e)
    return {}


def _dataforseo_auth() -> str:
    import base64 as _b64
    login = os.getenv("DATAFORSEO_LOGIN", "")
    pw = os.getenv("DATAFORSEO_PASSWORD", "")
    return _b64.b64encode(f"{login}:{pw}".encode()).decode("ascii")


def dataforseo_balance() -> Optional[float]:
    """Live account balance (USD) via DataForSEO's free user_data endpoint. None if unavailable."""
    try:
        res = _http.request_json(
            "GET", "https://api.dataforseo.com/v3/appendix/user_data",
            headers={"Authorization": f"Basic {_dataforseo_auth()}"},
            timeout=20, max_retries=1, guard_redirects=True)
        if res.ok and isinstance(res.data, dict):
            r = ((res.data.get("tasks") or [{}])[0].get("result") or [{}])[0]
            return float((r.get("money") or {}).get("balance"))
    except Exception:  # noqa: BLE001
        pass
    return None


_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def _dfs_location(geo: str) -> str:
    """DataForSEO location_name must be the canonical 'City,State,Country' form. Businesses store geo
    loosely ('Cincinnati, OH'), which DataForSEO REJECTS. Normalize 'City, ST' -> 'City,State,United
    States' (expanding the state abbreviation); fall back to national 'United States' if we can't.
    DATAFORSEO_LOCATION overrides everything (set an exact DataForSEO location_name to force it)."""
    override = (os.getenv("DATAFORSEO_LOCATION") or "").strip()
    if override:
        return override
    parts = [p.strip() for p in (geo or "").split(",") if p.strip()]
    if len(parts) == 2:
        city, st = parts
        state = _US_STATES.get(st.upper(), st)   # expand 'OH' -> 'Ohio'; leave full state names as-is
        return f"{city},{state},United States"
    return "United States"   # empty / non-'City, ST' geo -> national volume


def _dfs_labs_location(geo: str) -> str:
    """DataForSEO LABS endpoints (keyword_overview, ranked_keywords, ...) take a COUNTRY-level
    location_name — NOT the 'City,State' form the Google-Ads endpoint wants. Our keywords already
    bake in the geo ('financial advisor cincinnati'), so national volume of the geo-phrase is the
    right number. Defaults to United States; set DATAFORSEO_LOCATION for a different country."""
    return (os.getenv("DATAFORSEO_LOCATION") or "").strip() or "United States"


def _dfs_clean_kw(k: str) -> str:
    """Sanitize a keyword for DataForSEO's Google Ads endpoint, which rejects punctuation (?, !, etc.)
    and fails the ENTIRE batch on one bad term. Keep letters/numbers/spaces/&/- ; drop the rest.
    'How long does term life insurance pay out?' -> 'How long does term life insurance pay out'."""
    s = re.sub(r"[^0-9A-Za-z &\-]", " ", k or "")
    return re.sub(r"\s+", " ", s).strip()


def _dataforseo_volume(keywords: list[str], location: str, business_id: Optional[int] = None) -> dict:
    auth = _dataforseo_auth()
    # DEDUPE (case-insensitive, order-preserving) so we never pay to look up the same term twice, then
    # batch into the FEWEST possible calls: DataForSEO bills PER REQUEST (not per keyword) and accepts
    # up to 700 keywords/request, so N unique keywords cost exactly ceil(N/700) calls.
    seen: set = set()
    unique: list[str] = []
    for k in keywords:
        kl = (k or "").strip().lower()
        if kl and kl not in seen:
            seen.add(kl)
            unique.append(k.strip())
    if not unique:
        return {}
    try:
        floor = float(os.getenv("DATAFORSEO_MIN_BALANCE", "0.20") or 0)
    except (TypeError, ValueError):
        floor = 0.20
    _CHUNK = 700
    out: dict = {}
    for i in range(0, len(unique), _CHUNK):
        chunk = unique[i:i + _CHUNK]
        # Insufficient-funds guard BEFORE each paid call, so a multi-batch run stops cleanly instead
        # of failing mid-way when the balance runs low.
        if floor > 0:
            bal = dataforseo_balance()
            if bal is not None and bal < floor:
                log.warning("DataForSEO balance $%.2f < $%.2f floor -- stopping after %d keyword(s) "
                            "enriched. Top up to resume.", bal, floor, len(out))
                break
        # DataForSEO's Google Ads keywords reject punctuation ('?', '!', etc.) and one bad keyword
        # fails the WHOLE batch -> sanitize every term, and keep a cleaned->original map so results
        # (keyed by the cleaned term) update the original stored rows.
        clean_to_orig: dict = {}
        cleaned: list[str] = []
        for k in chunk:
            ck = _dfs_clean_kw(k)[:80]
            # DataForSEO Google Ads rejects keywords with >10 words (and one bad term fails the WHOLE
            # batch). Long-tail questions have no ad-volume data anyway -> skip them cleanly.
            if ck and len(ck.split()) <= 10:
                clean_to_orig.setdefault(ck.lower(), k)
                cleaned.append(ck)
        if not cleaned:
            continue
        # Labs keyword_overview: ~$0.012/batch (vs $0.09 for google_ads) AND returns REAL keyword
        # difficulty + search intent, not just competition. Same request shape; richer response.
        body = [{"keywords": cleaned, "location_name": _dfs_labs_location(location), "language_name": "English"}]
        res = _http.request_json(
            "POST", "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_overview/live",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            json=body, timeout=90, max_retries=2, guard_redirects=True)
        if not (res.ok and isinstance(res.data, dict)):
            log.warning("DataForSEO volume call failed: %s", getattr(res, "error", None) or getattr(res, "status", "?"))
            continue
        # DataForSEO returns the EXACT USD cost of the call -> record it per batch.
        try:
            from . import cost as _cost
            exact = res.data.get("cost")
            # DataForSEO returns the EXACT cost; a failed/empty call returns none -> record $0 (no
            # charge). Never fall back to a per-keyword estimate (that mis-multiplied failed calls).
            _cost.record_cost(business_id, None, "keyword_volume", "dataforseo", "labs/keyword_overview",
                              cost_usd=float(exact or 0),
                              units=len(chunk), unit_label="keywords",
                              detail={"keyword_count": len(chunk), "batch": i // _CHUNK + 1,
                                      "exact_cost": exact, "status": res.data.get("status_message")})
        except Exception:  # noqa: BLE001 -- cost logging must never break enrichment
            pass
        for task in res.data.get("tasks") or []:
            for result in (task.get("result") or []):
                for item in (result.get("items") or []):
                    kw = (item.get("keyword") or "").lower()   # the cleaned term DataForSEO echoes back
                    if not kw:
                        continue
                    orig = (clean_to_orig.get(kw) or kw).lower()   # map back to the original stored keyword
                    ki = item.get("keyword_info") or {}
                    kp = item.get("keyword_properties") or {}
                    si = item.get("search_intent_info") or {}
                    diff = kp.get("keyword_difficulty")
                    out[orig] = {"search_volume": ki.get("search_volume"),
                                 "keyword_difficulty": int(diff) if isinstance(diff, (int, float)) else None,
                                 "cpc": ki.get("cpc"),
                                 "intent": si.get("main_intent")}
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


def enrich_target_keywords(business_id: int) -> dict:
    """Batch-enrich EVERY stored target keyword for a business with real search volume / difficulty /
    CPC in the FEWEST possible provider calls. The keyword set is deduped and sent in one request per
    <=700 keywords (DataForSEO bills per request), so a typical business (<=45 keywords) costs exactly
    ONE call. Updates target_keywords in place. Dormant-safe (no provider -> skipped) + balance-guarded.
    Run:  python -m rep_engine.keyword_research enrich --business-id 1"""
    if not volume_configured():
        return {"skipped": True, "reason": "no keyword-volume provider set (KEYWORD_VOLUME_PROVIDER)"}
    with db() as conn:
        rows = conn.execute("SELECT DISTINCT keyword FROM target_keywords WHERE business_id=%s "
                            "AND keyword IS NOT NULL", (business_id,)).fetchall()
        biz = conn.execute("SELECT geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
    keywords = [r["keyword"] for r in rows if (r.get("keyword") or "").strip()]
    if not keywords:
        return {"skipped": True, "reason": "no target keywords to enrich yet — run keyword research first"}
    location = (biz.get("geo") if biz else "") or ""
    calls = (len(set(k.lower() for k in keywords)) + 699) // 700
    vol = _enrich_volume(keywords, location, business_id)   # dedupes + chunks internally
    updated = 0
    with db() as conn:
        for kw, v in vol.items():
            # intent from Labs is authoritative -> overwrite only when present (COALESCE keeps the
            # prior LLM-derived intent if DataForSEO didn't return one).
            updated += conn.execute(
                "UPDATE target_keywords SET search_volume=%s, keyword_difficulty=%s, cpc=%s, "
                "intent=COALESCE(%s, intent) WHERE business_id=%s AND lower(keyword)=%s",
                (v.get("search_volume"), v.get("keyword_difficulty"), v.get("cpc"),
                 v.get("intent"), business_id, kw.lower())).rowcount
        conn.commit()
    log.info("enrich_target_keywords biz %d: %d keywords -> %d enriched, %d rows updated, %d provider call(s)",
             business_id, len(keywords), len(vol), updated, calls)
    return {"keywords": len(keywords), "enriched": len(vol), "updated": updated,
            "provider_calls": calls, "provider": os.getenv("KEYWORD_VOLUME_PROVIDER")}


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
# Corporate-profile / employer-BRAND phrases that, for a small local business, almost always name a
# DIFFERENT (large) company. Deliberately NARROW: we do NOT drop generic "careers/jobs/salary/
# hiring" terms — those are legitimate targets for a RECRUITING business (e.g. a financial-services
# agency that recruits agents). Bare competitor brand names are handled by the competitor/contested
# list + the LLM relevance pass, not here.
_EMPLOYER_RE = re.compile(
    r"\b(good place to work|great place to work|good company to work|glassdoor|"
    r"stock price|who owns|headquarters|ceo of)\b",
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
    # A query that ALSO names THIS business is a query ABOUT this business -- e.g. a branded
    # reputation-defense term like "is <business> <parent company> legit" -- NOT an off-brand
    # query about a different company. Keep it even if it shares a contested/parent-company token.
    # (Before this guard, "is Team Unstoppable Primerica legit" was dropped because "primerica"
    # was a contested term, stripping the client's own #1 legitimacy queries.)
    names_client = bool(client_tokens & _name_tokens(n))
    if not names_client:
        # names another company (a competitor or a confusion entity) and NOT this business
        for b in blocked:
            if b and b in n:
                return True
    # employer-reputation / job-seeker / corporate-profile query about someone OTHER than the client
    if _EMPLOYER_RE.search(n) and not names_client:
        return True
    return False


_RELEVANCE_SYSTEM = (
    "You audit candidate SEO keywords for ONE specific business. Return STRICT JSON "
    "{\"drop\":[str,...]} listing the EXACT candidate strings to REMOVE because they are not "
    "relevant to THIS business: keywords that name a DIFFERENT company or brand (competitors or "
    "unrelated organizations), employer-reputation or job-seeker queries about other companies "
    "(e.g. 'is <other company> a good place to work', 'careers', 'glassdoor', 'salary'), or terms "
    "off-topic for this business's services and customers. KEEP everything relevant to THIS "
    "business — its own services, category, questions, location, and (if it recruits) its own "
    "careers/opportunity. CRITICALLY, KEEP branded reputation-defense queries that name THIS "
    "business (or its own parent company/brand): 'is <this business> legitimate / a scam / a "
    "pyramid scheme', '<this business> reviews / complaints', '<this business> <parent company> "
    "legit' — the business MUST own these, so NEVER drop a query that names this business. Only "
    "remove keywords that reference a DIFFERENT company or are clearly off-topic. If nothing "
    "should be removed, return {\"drop\":[]}."
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
        res = _llm.orchestrator_json(_RELEVANCE_SYSTEM, payload, tier="mid",
                                     bill={"business_id": ctx.get("business_id"), "operation": "keyword_relevance"})
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
    "You are a local-SEO AND reputation-defense keyword strategist. Given a business profile, what "
    "its own website already covers (and is MISSING), its competitors, and (if provided) the WORST "
    "queries AI assistants currently answer badly about it, propose the SEO keywords it should "
    "target to rank on Google locally, to DEFEND its reputation, AND to be understood/cited by AI "
    "assistants. Return STRICT JSON only: {\"keywords\":[{\"keyword\":str,\"kind\":\"reputation_defense"
    "|primary|secondary|local|question\",\"intent\":\"commercial|informational|local|navigational\","
    "\"rationale\":str}]}. Include: "
    "3-6 reputation_defense terms -- branded legitimacy/trust queries about THIS business BY NAME "
    "(and, if it operates under a parent company/brand, that name too), e.g. 'is <business> "
    "legitimate', 'is <business> a scam', 'is <business> a pyramid scheme', '<business> reviews', "
    "'<business> complaints', 'is <business> <parent company> legit', '<business> <parent company> "
    "reviews'. These are the queries people search when deciding whether to trust the business, so "
    "the business MUST own them -- ALWAYS include several even if the profile looks positive; "
    "2-4 primary service terms; several local terms (service + city, 'near me'); and 4-8 question "
    "keywords real customers ask (what they'd type or ask an AI). Keep them realistic and specific "
    "to this business + its area. Do NOT include OTHER companies' or competitors' brand names, or "
    "queries ABOUT another company (e.g. 'is <another company> a good place to work', a competitor's "
    "reviews / glassdoor / stock price). IMPORTANT: legitimacy/scam/reviews/complaints queries that "
    "name THIS business (or its own parent company/brand) are the POINT here -- INCLUDE them, do not "
    "treat them as off-brand. Keywords about THIS business's own services -- and, if it recruits, "
    "its own careers/opportunity -- are welcome. 12-20 keywords."
)


def _seed_llm(ctx: dict) -> list[dict]:
    payload = json.dumps(ctx)[:6000]
    res = _llm.orchestrator_json(_SEED_SYSTEM, payload, tier="mid",
                                 bill={"business_id": ctx.get("business_id"), "operation": "keyword_seed"})
    items = (res or {}).get("keywords") if isinstance(res, dict) else None
    out = []
    for it in (items or []):
        kw = (it.get("keyword") or "").strip() if isinstance(it, dict) else ""
        if not kw:
            continue
        kind = (it.get("kind") or "secondary").strip().lower()
        if kind not in _VALID_KINDS:
            kind = "secondary"
        out.append({
            "keyword": kw,
            "kind": kind,
            "source": "llm_seed",
            "intent": (it.get("intent") or "commercial"),
            "rationale": (it.get("rationale") or "")[:240],
        })
    return out


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------
def _weak_queries(conn, business_id: int) -> list[str]:
    """The prompts AI assistants currently answer badly about this business (gap model's
    weak_queries). These are the real questions reputation-defense keywords must cover, so we
    ground the seeder with them. Best-effort: returns [] if no gap model / column exists yet."""
    try:
        row = conn.execute(
            "SELECT model FROM gap_models WHERE business_id=%s ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
    except Exception:  # noqa: BLE001 -- gap model is optional grounding
        return []
    model = row["model"] if row else None
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except Exception:  # noqa: BLE001
            model = None
    if not isinstance(model, dict):
        return []
    out: list[str] = []
    for wq in (model.get("weak_queries") or []):
        p = (wq.get("prompt") if isinstance(wq, dict) else wq) or ""
        p = p.strip()
        if p:
            out.append(p)
    # de-dup, preserve order, bound the payload
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq[:12]


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
        weak = _weak_queries(conn, business_id)
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
        "business_id": business_id,   # carried so the LLM seed/relevance calls can meter their spend
        "name": b["name"], "industry": b.get("industry"), "services": b.get("services"),
        "geo": b.get("geo"), "goal": b.get("goal"), "contested_terms": b.get("contested_terms"),
        "site_missing_topics": sorted(set(missing))[:12],
        "competitors": [c["name"] for c in comps],
        "weak_ai_queries": weak,
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

    # Rank, then cap the long_tail share so Serper's relatedSearches/autocomplete (all classified
    # long_tail) can't crowd out the primary/local/question/reputation_defense terms that matter.
    ordered = sorted(candidates.values(),
                     key=lambda x: _KIND_PRIORITY.get(x.get("kind", ""), 0), reverse=True)
    ranked, long_tail_kept = [], 0
    for it in ordered:
        if it.get("kind") == "long_tail":
            if long_tail_kept >= _MAX_LONG_TAIL:
                continue
            long_tail_kept += 1
        ranked.append(it)
        if len(ranked) >= _MAX_STORED:
            break

    # CI-5: enrich with real search volume / difficulty when a provider key is set (dormant otherwise).
    vol = _enrich_volume([it["keyword"] for it in ranked], location, business_id)

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
           "reputation_defense": sum(1 for it in ranked if it.get("kind") == "reputation_defense"),
           "long_tail": long_tail_kept, "weak_queries_grounded": len(ctx.get("weak_ai_queries") or []),
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
