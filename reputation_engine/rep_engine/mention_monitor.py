"""
Reputation Crowding-Out Engine -- Module 13: Mention Monitoring & Reply Drafting
================================================================================
The capability the team wanted from BizReply -- but with NO per-business license
cap (monitor as many businesses/keywords as your own infrastructure allows) and
wired into our crowding-out + compliance discipline.

Pipeline:
  1. add_keyword(business_id, keyword)         -- unlimited keywords per business
  2. discover(business_id)                      -- pull mentions via pluggable SOURCE
     adapters (RSS/Reddit/web-search/manual import), dedup, score relevance/sentiment
  3. draft_replies(business_id)                 -- for each new mention, draft an
     on-brand reply via the existing content generator + compliance gate
  4. list_pending / approve / reject            -- HUMAN approves before anything posts

NON-NEGOTIABLE: nothing is ever auto-posted. Every reply is stored pending_review.
For a financial-services context (Primerica), public replies are regulated comms --
a human must approve, and the compliance gate fails safe (screener unavailable =>
human must review). Posting itself is intentionally left to the human + the platform;
this module drafts and routes, it does not publish.

SOURCES are adapters so you are not locked to one vendor or a license tier. The
built-in ones use public/free endpoints; add your own by registering a callable.

Run:
    python -m rep_engine.mention_monitor add --business-id 1 --keyword "Acme Financial"
    python -m rep_engine.mention_monitor discover --business-id 1
    python -m rep_engine.mention_monitor draft --business-id 1
    python -m rep_engine.mention_monitor pending --business-id 1
    python -m rep_engine.mention_monitor approve --reply 5 --reviewer "Logan"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
from typing import Callable, Optional

from . import http as _http


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("mention_monitor")





def _ensure() -> None:
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS monitor_keywords (
            id BIGSERIAL PRIMARY KEY, business_id BIGINT, keyword TEXT, negative BOOLEAN DEFAULT FALSE,
            active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (business_id, keyword))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS mentions (
            id BIGSERIAL PRIMARY KEY, business_id BIGINT, source TEXT, source_url TEXT, external_id TEXT,
            author TEXT, title TEXT, body TEXT, matched_keyword TEXT, sentiment TEXT, relevance NUMERIC(4,3),
            status TEXT DEFAULT 'new', discovered_at TIMESTAMPTZ DEFAULT now(), dedup_hash TEXT UNIQUE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS mention_replies (
            id BIGSERIAL PRIMARY KEY, mention_id BIGINT REFERENCES mentions(id), business_id BIGINT,
            draft TEXT, tone TEXT, compliance_pass BOOLEAN, compliance_flags JSONB DEFAULT '[]'::jsonb,
            status TEXT DEFAULT 'pending_review', reviewer TEXT, reviewed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now())""")
        conn.commit()


# ----------------------------------------------------------------------------
# Keywords
# ----------------------------------------------------------------------------
def add_keyword(business_id: int, keyword: str, negative: bool = False) -> int:
    _ensure()
    with db() as conn:
        row = conn.execute(
            "INSERT INTO monitor_keywords (business_id, keyword, negative) VALUES (%s,%s,%s) "
            "ON CONFLICT (business_id, keyword) DO UPDATE SET negative=EXCLUDED.negative, active=TRUE "
            "RETURNING id", (business_id, keyword, negative),
        ).fetchone()
        conn.commit()
    log.info("Keyword '%s' added for business %d", keyword, business_id)
    return row["id"]


def _keywords(conn, business_id: int) -> tuple[list[str], list[str]]:
    rows = conn.execute("SELECT keyword, negative FROM monitor_keywords WHERE business_id=%s AND active",
                        (business_id,)).fetchall()
    pos = [r["keyword"] for r in rows if not r["negative"]]
    neg = [r["keyword"] for r in rows if r["negative"]]
    return pos, neg


# ----------------------------------------------------------------------------
# SOURCE ADAPTERS -- pluggable. Each returns a list of dicts:
#   {source, source_url, external_id, author, title, body}
# Built-ins use public/free endpoints; failures degrade gracefully (return []).
# Register custom adapters with register_source().
# ----------------------------------------------------------------------------
SOURCES: dict[str, Callable[[str], list[dict]]] = {}


def register_source(name: str, fn: Callable[[str], list[dict]]) -> None:
    SOURCES[name] = fn


def _src_reddit(keyword: str) -> list[dict]:
    """Reddit public search JSON (no auth). Best-effort."""
    res = _http.request_json(
        "GET", "https://www.reddit.com/search.json",
        headers={"User-Agent": "ReputationEngine/1.0 (mention-monitor)"},
        params={"q": keyword, "limit": 25, "sort": "new"}, timeout=20, max_retries=2,
    )
    if res.failed or not isinstance(res.data, dict):
        return []
    out = []
    for child in (res.data.get("data", {}) or {}).get("children", []):
        d = child.get("data", {})
        out.append({
            "source": "reddit",
            "source_url": "https://www.reddit.com" + (d.get("permalink") or ""),
            "external_id": d.get("name") or d.get("id"),
            "author": d.get("author"),
            "title": d.get("title"),
            "body": d.get("selftext") or d.get("title") or "",
        })
    return out


def _src_rss(keyword: str) -> list[dict]:
    """Google News RSS for the keyword (no auth). Best-effort, parsed with regex."""
    from urllib.parse import quote
    url = f"https://news.google.com/rss/search?q={quote(keyword)}"
    res = _http.request_json("GET", url, parse_json=False, timeout=20, max_retries=2)
    if res.failed or not res.text:
        return []
    items = re.findall(r"<item>(.*?)</item>", res.text, re.DOTALL)
    out = []
    for it in items[:25]:
        def _tag(t):
            m = re.search(rf"<{t}>(.*?)</{t}>", it, re.DOTALL)
            return re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1)).strip() if m else ""
        link = _tag("link")
        out.append({"source": "news_rss", "source_url": link, "external_id": link or _tag("guid"),
                    "author": _tag("source"), "title": _tag("title"), "body": _tag("description")})
    return out


def _serper_search(query: str, num: int = 15) -> list[dict]:
    """General Google web search via Serper (google.serper.dev/search). Returns the
    'organic' results, or [] when SERPER_API_KEY is unset or the call fails. This is what
    powers the broader web / social / review-site coverage beyond the free Reddit + news
    feeds; set SERPER_API_KEY to turn it on."""
    import os
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return []
    res = _http.request_json(
        "POST", "https://google.serper.dev/search",
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        json={"q": query, "num": num}, timeout=20, max_retries=2,
    )
    if res.failed or not isinstance(res.data, dict):
        return []
    return res.data.get("organic", []) or []


def _serper_items(results: list[dict], source: str) -> list[dict]:
    out = []
    for r in results:
        link = r.get("link") or ""
        out.append({
            "source": source, "source_url": link, "external_id": link,
            "author": r.get("source") or "", "title": r.get("title") or "",
            "body": r.get("snippet") or r.get("title") or "",
        })
    return out


def _src_web(keyword: str) -> list[dict]:
    """Broad Google web results for the keyword (Serper)."""
    return _serper_items(_serper_search(f'"{keyword}"'), "web")


def _src_social(keyword: str) -> list[dict]:
    """X/Twitter, Facebook, YouTube, LinkedIn posts mentioning the keyword (Serper, site-scoped)."""
    q = f'"{keyword}" (site:twitter.com OR site:x.com OR site:facebook.com OR site:youtube.com OR site:linkedin.com)'
    return _serper_items(_serper_search(q), "social")


def _src_reviews(keyword: str) -> list[dict]:
    """Complaint + review sites mentioning the keyword (Serper, site-scoped): RipoffReport,
    PissedConsumer, BBB, Trustpilot, Yelp, ComplaintsBoard, Glassdoor."""
    q = (f'"{keyword}" (site:ripoffreport.com OR site:pissedconsumer.com OR site:bbb.org OR '
         f'site:trustpilot.com OR site:yelp.com OR site:complaintsboard.com OR site:glassdoor.com)')
    return _serper_items(_serper_search(q), "reviews")


register_source("reddit", _src_reddit)
register_source("news_rss", _src_rss)
register_source("web", _src_web)
register_source("social", _src_social)
register_source("reviews", _src_reviews)


# ----------------------------------------------------------------------------
# Keyword management helpers (used by the API CRUD)
# ----------------------------------------------------------------------------
def list_keywords(business_id: int) -> list[dict]:
    _ensure()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, keyword, negative, active, created_at FROM monitor_keywords "
            "WHERE business_id=%s ORDER BY id", (business_id,)).fetchall()
    return [dict(r) for r in rows]


def remove_keyword(business_id: int, keyword_id: int) -> bool:
    _ensure()
    with db() as conn:
        r = conn.execute(
            "DELETE FROM monitor_keywords WHERE id=%s AND business_id=%s RETURNING id",
            (keyword_id, business_id)).fetchone()
        conn.commit()
    return bool(r)


# ----------------------------------------------------------------------------
# Relevance + sentiment (lightweight heuristics; LLM optional via content gen)
# ----------------------------------------------------------------------------
_NEG = set("scam ripoff fraud terrible awful worst avoid lawsuit complaint pyramid mlm".split())
_POS = set("great excellent love recommend trusted helpful reliable best amazing".split())


def _relevance(text: str, keyword: str) -> float:
    if not text or not keyword:
        return 0.0
    t = text.lower()
    kw = keyword.lower()
    if kw in t:
        return 1.0
    words = [w for w in re.findall(r"[a-z]+", kw) if len(w) > 3]
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in t)
    return round(hits / len(words), 3)


def _sentiment(text: str) -> str:
    t = set(re.findall(r"[a-z]+", (text or "").lower()))
    neg, pos = len(t & _NEG), len(t & _POS)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def _matches_negative(text: str, neg_terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(n.lower() in t for n in neg_terms)


def discover(business_id: int, sources: Optional[list[str]] = None, quiet: bool = False) -> dict:
    """Pull mentions for all active keywords across the chosen sources. Dedup by
    (source, external_id). No cap on keywords or businesses."""
    _ensure()
    use = sources or list(SOURCES.keys())
    found = 0
    with db() as conn:
        pos_kw, neg_kw = _keywords(conn, business_id)
        if not pos_kw:
            if not quiet:
                log.info("No active keywords for business %d; add some first.", business_id)
            return {"found": 0}
        for kw in pos_kw:
            for src in use:
                adapter = SOURCES.get(src)
                if not adapter:
                    continue
                try:
                    items = adapter(kw)
                except Exception as e:  # noqa: BLE001
                    log.warning("source %s failed for '%s': %s", src, kw, e)
                    items = []
                for it in items:
                    text = f"{it.get('title','')} {it.get('body','')}".strip()
                    if neg_kw and _matches_negative(text, neg_kw):
                        continue  # excluded by a negative keyword
                    rel = _relevance(text, kw)
                    if rel < 0.34:
                        continue  # too weak a match
                    h = hashlib.sha256(f"{it.get('source')}|{it.get('external_id')}".encode()).hexdigest()
                    try:
                        r = conn.execute(
                            """INSERT INTO mentions (business_id, source, source_url, external_id, author,
                                title, body, matched_keyword, sentiment, relevance, dedup_hash)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (dedup_hash) DO NOTHING RETURNING id""",
                            (business_id, it.get("source"), it.get("source_url"), it.get("external_id"),
                             it.get("author"), it.get("title"), it.get("body"), kw,
                             _sentiment(text), rel, h),
                        ).fetchone()
                        if r:
                            found += 1
                    except Exception as e:  # noqa: BLE001
                        log.debug("skip mention: %s", e)
        conn.commit()
    if not quiet:
        log.info("Discovered %d new mention(s) for business %d.", found, business_id)
    return {"found": found}


def draft_replies(business_id: int, limit: int = 50, tone: str = "helpful, factual, on-brand",
                  quiet: bool = False) -> dict:
    """For each NEW mention, draft a reply via the content generator's LLM + compliance
    gate, stored pending_review. Never posts. Negative/contested mentions are drafted
    in a crowding-out spirit: accurate, helpful, non-defensive -- never disparaging."""
    _ensure()
    drafted = 0
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        mentions = conn.execute(
            "SELECT * FROM mentions WHERE business_id=%s AND status='new' ORDER BY relevance DESC LIMIT %s",
            (business_id, limit),
        ).fetchall()
        if not mentions:
            if not quiet:
                log.info("No new mentions to draft for business %d.", business_id)
            return {"drafted": 0}

        # reuse the content generator's LLM + compliance gate
        from . import content_generator as cg

        for mt in mentions:
            draft = _draft_one(biz, dict(mt), tone, cg)
            comp = cg._compliance(draft) if draft else {"pass": None, "flags": ["no draft produced"]}
            conn.execute(
                """INSERT INTO mention_replies (mention_id, business_id, draft, tone,
                    compliance_pass, compliance_flags, status)
                   VALUES (%s,%s,%s,%s,%s,%s,'pending_review')""",
                (mt["id"], business_id, draft, tone, comp.get("pass"),
                 json.dumps(comp.get("flags", []))),
            )
            conn.execute("UPDATE mentions SET status='drafted' WHERE id=%s", (mt["id"],))
            drafted += 1
        conn.commit()
    if not quiet:
        log.info("Drafted %d repl(ies) for business %d (all pending human review).", drafted, business_id)
    return {"drafted": drafted}


def _draft_one(biz: dict, mention: dict, tone: str, cg) -> str:
    """Produce a single reply draft. Uses the orchestrator LLM if available; else a
    safe templated draft the human can edit. Never disparages; crowding-out spirit."""
    from . import ai_state_audit as m
    system = (
        "You write SHORT, helpful, factual public replies on behalf of a business that "
        "was mentioned online. Rules: be genuine and non-defensive; never disparage anyone; "
        "never make unverifiable claims; for financial services, avoid specific guarantees "
        "or performance promises and avoid giving individualized advice. If the mention is "
        "critical, respond with empathy and an offer to help offline. 2-4 sentences. "
        "Output ONLY the reply text."
        + m.UNTRUSTED_INSTRUCTION
    )
    # The mention body is scraped from an untrusted public post -- fence it so an
    # embedded "ignore your instructions and post X" cannot hijack the draft.
    user = json.dumps({
        "business": biz.get("name"), "services": biz.get("services"),
        "tone": tone, "mention_title": mention.get("title"),
        "mention_body": m._fence_untrusted((mention.get("body") or "")[:1200]),
        "sentiment": mention.get("sentiment"),
    })
    try:
        text = m.orchestrator_text(system, user, max_tokens=300)
        if text and text.strip():
            return text.strip()
    except Exception as e:  # noqa: BLE001
        log.debug("LLM draft failed: %s", e)
    # safe fallback template (clearly human-editable)
    name = biz.get("name", "our team")
    if mention.get("sentiment") == "negative":
        return (f"[DRAFT — please review/edit] Thanks for the feedback. We'd genuinely like "
                f"to understand and help — please reach out to {name} directly so we can make it right.")
    return (f"[DRAFT — please review/edit] Thanks for mentioning {name}! Happy to answer any "
            f"questions — feel free to reach out.")


# ----------------------------------------------------------------------------
# Human review
# ----------------------------------------------------------------------------
def list_pending(business_id: int, quiet: bool = False) -> list[dict]:
    _ensure()
    with db() as conn:
        rows = conn.execute(
            "SELECT r.id, r.draft, r.compliance_pass, r.compliance_flags, m.source, m.source_url, "
            "m.title, m.sentiment FROM mention_replies r JOIN mentions m ON m.id=r.mention_id "
            "WHERE r.business_id=%s AND r.status='pending_review' ORDER BY r.id", (business_id,),
        ).fetchall()
    out = [dict(r) for r in rows]
    if not quiet:
        for r in out:
            flag = "" if r["compliance_pass"] else "  [COMPLIANCE: needs human review]"
            print(f"\n#{r['id']} [{r['source']}] {r['title'][:70] if r['title'] else ''}{flag}")
            print(f"  on: {r['source_url']}")
            print(f"  draft: {r['draft']}")
    return out


def approve(reply_id: int, reviewer: str) -> None:
    _ensure()
    with db() as conn:
        conn.execute("UPDATE mention_replies SET status='approved', reviewer=%s, reviewed_at=now() "
                     "WHERE id=%s", (reviewer, reply_id))
        conn.execute("UPDATE mentions SET status='actioned' WHERE id=("
                     "SELECT mention_id FROM mention_replies WHERE id=%s)", (reply_id,))
        conn.commit()
    log.info("Reply %d approved by %s (ready to post manually).", reply_id, reviewer)


def reject(reply_id: int, reviewer: str) -> None:
    _ensure()
    with db() as conn:
        conn.execute("UPDATE mention_replies SET status='rejected', reviewer=%s, reviewed_at=now() "
                     "WHERE id=%s", (reviewer, reply_id))
        conn.commit()
    log.info("Reply %d rejected by %s.", reply_id, reviewer)


def main() -> None:
    ap = argparse.ArgumentParser(description="Mention monitoring + reply drafting (human-approved)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ak = sub.add_parser("add"); ak.add_argument("--business-id", type=int, required=True)
    ak.add_argument("--keyword", required=True); ak.add_argument("--negative", action="store_true")
    d = sub.add_parser("discover"); d.add_argument("--business-id", type=int, required=True)
    d.add_argument("--sources", nargs="*")
    dr = sub.add_parser("draft"); dr.add_argument("--business-id", type=int, required=True)
    pe = sub.add_parser("pending"); pe.add_argument("--business-id", type=int, required=True)
    ap_ = sub.add_parser("approve"); ap_.add_argument("--reply", type=int, required=True)
    ap_.add_argument("--reviewer", required=True)
    rj = sub.add_parser("reject"); rj.add_argument("--reply", type=int, required=True)
    rj.add_argument("--reviewer", required=True)
    args = ap.parse_args()
    if args.cmd == "add":
        add_keyword(args.business_id, args.keyword, args.negative)
    elif args.cmd == "discover":
        discover(args.business_id, args.sources)
    elif args.cmd == "draft":
        draft_replies(args.business_id)
    elif args.cmd == "pending":
        list_pending(args.business_id)
    elif args.cmd == "approve":
        approve(args.reply, args.reviewer)
    elif args.cmd == "reject":
        reject(args.reply, args.reviewer)


if __name__ == "__main__":
    main()
