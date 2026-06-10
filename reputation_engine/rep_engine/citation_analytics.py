"""
Reputation Crowding-Out Engine -- Module 10: Citation Analytics
===============================================================
Implements the OpenCite-style metrics that were the most differentiating gap:
  - SHARE OF VOICE: which domains AI engines actually cite when answering about the
    business, and what fraction each holds.
  - CITATION MOMENTUM: how each domain's presence shifts run-over-run (rising,
    falling, newly-appearing, dropped) -- so you can show a contested source losing
    ground and owned/neutral sources gaining it.
  - PERSONA / LOCATION LENSES: how the answer (and its citations) differ for
    different asker personas and locations -- which matters enormously for a LOCAL
    business ("what does someone asking from Cincinnati actually see?").

This reads the `answers` rows the audit already records (which carry cited_sources,
and now persona/location), classifies each cited domain as owned/contested/neutral,
and writes per-run citation_momentum. It NEVER fabricates citations; it only
measures what the engines returned.

Honesty/ethics: this is measurement, not manipulation. "Share of voice" here means
how often accurate/owned sources are surfaced vs. contested ones -- the goal remains
to out-surface (drown out), never to suppress legitimate sources.

Run:
    python -m rep_engine.citation_analytics analyze --business-id 1
    python -m rep_engine.citation_analytics momentum --business-id 1
    python -m rep_engine.citation_analytics personas --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from urllib.parse import urlparse


try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("citation_analytics")





def _ensure() -> None:
    with db() as conn:
        conn.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS persona TEXT DEFAULT ''")
        conn.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''")
        conn.execute("""CREATE TABLE IF NOT EXISTS citation_momentum (
            id BIGSERIAL PRIMARY KEY, business_id BIGINT, domain TEXT, run_id BIGINT,
            cite_count INT, share NUMERIC(6,4), classification TEXT,
            first_seen_run BIGINT, last_seen_run BIGINT, created_at TIMESTAMPTZ DEFAULT now())""")
        conn.commit()


def _strip_www(d: str) -> str:
    """Strip a leading 'www.' prefix. NOT str.lstrip('www.'), which strips any
    leading run of the chars {w,.} and would mangle e.g. 'weather.com' -> 'eather.com'."""
    return d[4:] if d.startswith("www.") else d


def _domain(src) -> str:
    """Extract a bare domain from a source entry (str URL or dict)."""
    if isinstance(src, dict):
        src = src.get("url") or src.get("domain") or src.get("link") or ""
    if not isinstance(src, str) or not src:
        return ""
    if "//" not in src:
        src = "//" + src
    netloc = urlparse(src).netloc or ""
    return _strip_www(netloc.lower()) if netloc else ""


def _classify(domain: str, biz: dict) -> str:
    """owned | contested | neutral. Owned = the business's own domain; contested =
    domain looks tied to a contested term; else neutral."""
    if not domain:
        return "unknown"
    own = _strip_www((biz.get("domain") or "").lower())
    if own and own in domain:
        return "owned"
    # Curated complaint-site markers stay broad (raw substring) -- a deliberate
    # heuristic (e.g. 'ripoff' must still catch 'ripoffreport.com').
    contested_markers = ["ripoff", "complaint", "scam", "pissedconsumer", "mlmwatch"]
    if any(m in domain for m in contested_markers):
        return "contested"
    # User-supplied contested terms match on whole domain LABELS/tokens, not raw
    # substring, so an arbitrary term ('mlm', 'scam', ...) no longer mis-flags a
    # legitimate domain that merely contains it (e.g. 'scamadviser.com').
    contested_terms = [t.strip().lower() for t in (biz.get("contested_terms") or "").split(",") if t.strip()]
    tokens = set(re.findall(r"[a-z0-9]+", domain.lower()))
    if any(t in tokens for t in contested_terms):
        return "contested"
    return "neutral"


def _citations_for_run(conn, run_id: int, biz: dict, persona: str = "", location: str = "") -> dict:
    """Aggregate cited domains for a run (optionally filtered to a persona/location)."""
    q = ("SELECT cited_sources FROM answers WHERE run_id=%s AND NOT COALESCE(failed,false)")
    params = [run_id]
    if persona:
        q += " AND persona=%s"; params.append(persona)
    if location:
        q += " AND location=%s"; params.append(location)
    rows = conn.execute(q, params).fetchall()
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        srcs = r["cited_sources"]
        items = srcs if isinstance(srcs, list) else (json.loads(srcs) if srcs else [])
        for s in items:
            d = _domain(s)
            if d:
                counts[d] += 1
    total = sum(counts.values())
    out = []
    for d, c in counts.items():
        out.append({"domain": d, "count": c, "share": round(c / total, 4) if total else 0.0,
                    "classification": _classify(d, biz)})
    out.sort(key=lambda x: x["count"], reverse=True)
    return {"total_citations": total, "domains": out}


def analyze(business_id: int, quiet: bool = False) -> dict:
    """Compute share-of-voice for the latest run and persist citation_momentum rows."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        if not biz:
            raise SystemExit(f"No business id {business_id}")
        run = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                           "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        if not run:
            if not quiet:
                log.info("No completed run to analyze.")
            return {}
        rid = run["id"]
        cites = _citations_for_run(conn, rid, dict(biz))

        # share-of-voice by classification
        sov = defaultdict(float)
        for d in cites["domains"]:
            sov[d["classification"]] += d["share"]
        sov = {k: round(v, 4) for k, v in sov.items()}

        # persist momentum rows (with first/last seen lookups)
        for d in cites["domains"]:
            prev = conn.execute(
                "SELECT MIN(run_id) f FROM citation_momentum WHERE business_id=%s AND domain=%s",
                (business_id, d["domain"]),
            ).fetchone()
            first_seen = prev["f"] if prev and prev["f"] else rid
            conn.execute(
                """INSERT INTO citation_momentum
                   (business_id, domain, run_id, cite_count, share, classification, first_seen_run, last_seen_run)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (business_id, d["domain"], rid, d["count"], d["share"], d["classification"], first_seen, rid),
            )
        conn.commit()

    result = {
        "business": biz["name"],
        "run_id": rid,
        "total_citations": cites["total_citations"],
        "share_of_voice": sov,
        "top_domains": cites["domains"][:12],
        "interpretation": (
            "Share of voice shows how AI engines distribute their citations across "
            "owned, neutral, and contested sources. The goal of crowding-out is to grow "
            "the owned+neutral share so accurate sources dominate -- not to remove the "
            "contested ones."
        ),
    }
    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def momentum(business_id: int, quiet: bool = False) -> dict:
    """Compare citation share across the two most recent runs -> rising/falling/new/dropped."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        runs = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                            "ORDER BY id DESC LIMIT 2", (business_id,)).fetchall()
        if len(runs) < 2:
            if not quiet:
                log.info("Need two completed runs for momentum.")
            return {}
        cur = _citations_for_run(conn, runs[0]["id"], dict(biz))
        prev = _citations_for_run(conn, runs[1]["id"], dict(biz))

    cur_share = {d["domain"]: d for d in cur["domains"]}
    prev_share = {d["domain"]: d for d in prev["domains"]}
    all_domains = set(cur_share) | set(prev_share)
    movements = []
    for dom in all_domains:
        c = cur_share.get(dom, {}).get("share", 0.0)
        p = prev_share.get(dom, {}).get("share", 0.0)
        cls = (cur_share.get(dom) or prev_share.get(dom))["classification"]
        if p == 0 and c > 0:
            state = "new"
        elif c == 0 and p > 0:
            state = "dropped"
        elif c > p:
            state = "rising"
        elif c < p:
            state = "falling"
        else:
            state = "stable"
        movements.append({"domain": dom, "classification": cls,
                          "prev_share": round(p, 4), "current_share": round(c, 4),
                          "delta": round(c - p, 4), "state": state})
    movements.sort(key=lambda x: x["delta"], reverse=True)

    result = {"business": biz["name"], "movements": movements,
              "summary": {
                  "owned_or_neutral_gainers": [m["domain"] for m in movements
                                               if m["delta"] > 0 and m["classification"] in ("owned", "neutral")],
                  "contested_losers": [m["domain"] for m in movements
                                       if m["delta"] < 0 and m["classification"] == "contested"],
              }}
    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def personas(business_id: int, quiet: bool = False) -> dict:
    """Compare share-of-voice across persona/location lenses present in the latest run."""
    _ensure()
    with db() as conn:
        biz = conn.execute("SELECT * FROM businesses WHERE id=%s", (business_id,)).fetchone()
        run = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                           "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        if not run:
            return {}
        rid = run["id"]
        combos = conn.execute(
            "SELECT DISTINCT persona, location FROM answers WHERE run_id=%s", (rid,)
        ).fetchall()
        lenses = []
        for combo in combos:
            persona, location = combo["persona"] or "", combo["location"] or ""
            cites = _citations_for_run(conn, rid, dict(biz), persona, location)
            sov = defaultdict(float)
            for d in cites["domains"]:
                sov[d["classification"]] += d["share"]
            lenses.append({"persona": persona or "(generic)", "location": location or "(generic)",
                           "total_citations": cites["total_citations"],
                           "share_of_voice": {k: round(v, 4) for k, v in sov.items()},
                           "top_domain": cites["domains"][0]["domain"] if cites["domains"] else None})
    result = {"business": biz["name"], "run_id": rid, "lenses": lenses,
              "note": "Differences across lenses show whether some audiences/locations "
                      "see a more contested picture than others -- useful for a local business."}
    if not quiet:
        print(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Citation analytics (share of voice, momentum, persona/location)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "momentum", "personas"):
        p = sub.add_parser(name); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    {"analyze": analyze, "momentum": momentum, "personas": personas}[args.cmd](args.business_id)


if __name__ == "__main__":
    main()
