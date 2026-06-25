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
        conn.commit()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------------------
# Serper grounding (real Google data)
# ---------------------------------------------------------------------------
def _serper(endpoint: str, body: dict) -> Optional[dict]:
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return None
    res = _http.request_json(
        "POST", f"{SERPER_BASE}/{endpoint}",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json=body, timeout=20, max_retries=2,
    )
    if res.failed or not isinstance(res.data, dict):
        return None
    return res.data


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
    "to this business + its area. 10-18 keywords."
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

    # Rank + cap.
    ranked = sorted(candidates.values(),
                    key=lambda x: _KIND_PRIORITY.get(x.get("kind", ""), 0), reverse=True)[:_MAX_STORED]

    with db() as conn:
        # refresh the set (a re-run reflects the latest crawl/competitors)
        conn.execute("DELETE FROM target_keywords WHERE business_id=%s", (business_id,))
        for it in ranked:
            conn.execute(
                "INSERT INTO target_keywords (business_id, keyword, kind, source, intent, priority, rationale) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (business_id, keyword) DO UPDATE SET "
                "kind=EXCLUDED.kind, source=EXCLUDED.source, intent=EXCLUDED.intent, priority=EXCLUDED.priority",
                (business_id, it["keyword"][:200], it.get("kind"), it.get("source"),
                 it.get("intent"), _KIND_PRIORITY.get(it.get("kind", ""), 50), it.get("rationale")),
            )
        conn.commit()
    out = {"seeds": len(seeds), "serper_candidates": expanded_n, "stored": len(ranked),
           "serper_used": bool(os.getenv("SERPER_API_KEY"))}
    log.info("keyword research biz %d: %s", business_id, out)
    return out


def latest(business_id: int) -> list[dict]:
    """The stored target keywords for a business, highest priority first (for the UI/report)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT keyword, kind, source, intent, priority, rationale FROM target_keywords "
            "WHERE business_id=%s ORDER BY priority DESC NULLS LAST, keyword", (business_id,)).fetchall()
    return [dict(r) for r in rows]


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
