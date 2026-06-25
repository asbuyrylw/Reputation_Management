"""
Reputation Crowding-Out Engine -- Google review / rating ingestion (NEXT)
========================================================================
Reads the client's ACTUAL Google rating, review count, and (best-effort) recent review text via
Serper's places data -- the foundational local-reputation signal the product recommended acting on
but never measured. Read-only (no OAuth): the Integrations Phase 3 design later adds OAuth-connected
ingestion + reply posting on top of the same `reviews` table.

Sentiment is derived from the star rating (<=2 negative, 3 neutral, >=4 positive), matching the
design of record. Each ingest also writes a `gbp_snapshots` row so rating/count VELOCITY is derivable.

Run:
    python -m rep_engine.gbp_reviews ingest --business-id 2
    python -m rep_engine.gbp_reviews show   --business-id 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from typing import Optional

try:
    from .db import db
    from . import http as _http
except ImportError:  # pragma: no cover -- loose-script fallback
    from db import db  # type: ignore
    import http as _http  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("gbp_reviews")

SERPER_BASE = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")


def _serper(endpoint: str, body: dict) -> Optional[dict]:
    key = os.getenv("SERPER_API_KEY", "")
    if not key:
        return None
    res = _http.request_json("POST", f"{SERPER_BASE}/{endpoint}",
                             headers={"X-API-KEY": key, "Content-Type": "application/json"},
                             json=body, timeout=20, max_retries=2)
    if res.failed or not isinstance(res.data, dict):
        return None
    return res.data


def _sentiment(rating: Optional[float]) -> Optional[str]:
    if rating is None:
        return None
    return "negative" if rating <= 2 else "neutral" if rating < 4 else "positive"


def _norm_tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def _best_place(places: list[dict], name: str) -> Optional[dict]:
    """Pick the place whose title best matches the business name (token overlap), else the first."""
    want = _norm_tokens(name)
    best, best_score = None, -1
    for p in places:
        score = len(want & _norm_tokens(p.get("title", "")))
        if score > best_score:
            best, best_score = p, score
    return best


def ingest(business_id: int) -> dict:
    """Snapshot the business's Google rating + review count, and ingest recent reviews."""
    with db() as conn:
        b = conn.execute("SELECT name, geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not b:
        return {"skipped": True, "reason": "no business"}
    if not os.getenv("SERPER_API_KEY"):
        return {"skipped": True, "reason": "SERPER_API_KEY not set"}
    name, geo = b["name"], (b.get("geo") or "")
    data = _serper("places", {"q": f"{name} {geo}".strip(), "gl": "us"})
    places = (data or {}).get("places") or []
    place = _best_place(places, name) if places else None
    if not place:
        return {"skipped": True, "reason": "no matching Google place found"}
    rating = place.get("rating")
    count = place.get("ratingCount") or place.get("reviews") or place.get("ratingCount")
    cid = place.get("cid") or place.get("placeId") or place.get("fid")
    # 1. aggregate snapshot (enables the rating/velocity trend)
    with db() as conn:
        conn.execute(
            "INSERT INTO gbp_snapshots (business_id, rating, review_count, place_name, cid) "
            "VALUES (%s,%s,%s,%s,%s)",
            (business_id, rating, int(count) if isinstance(count, (int, float)) else None,
             place.get("title"), str(cid) if cid else None))
        conn.commit()
    # 2. per-review rows (best-effort: Serper reviews endpoint; aggregate already stored if this fails)
    ingested = 0
    if cid:
        rev = _serper("reviews", {"cid": str(cid)}) or _serper("reviews", {"placeId": str(cid)})
        items = (rev or {}).get("reviews") or []
        for r in items[:30]:
            rr = r.get("rating")
            author = (r.get("user") or {}).get("name") if isinstance(r.get("user"), dict) else r.get("user") or r.get("author")
            bodytxt = r.get("snippet") or r.get("text") or r.get("body") or ""
            ext = str(r.get("id") or r.get("reviewId") or "")
            dedup = hashlib.sha256(
                f"gbp|{cid}|{ext or (str(author) + bodytxt[:80])}".encode()).hexdigest()
            try:
                with db() as conn:
                    row = conn.execute(
                        "INSERT INTO reviews (business_id, source, external_id, location_ref, author, "
                        "rating, body, review_url, sentiment, dedup_hash, meta) "
                        "VALUES (%s,'google_business_profile',%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (dedup_hash) DO UPDATE SET last_seen_at=now() RETURNING id",
                        (business_id, ext or None, str(cid), author, rr, bodytxt,
                         r.get("link") or place.get("link"), _sentiment(rr), dedup,
                         json.dumps({"date": r.get("date")})),
                    ).fetchone()
                    conn.commit()
                if row:
                    ingested += 1
            except Exception as e:  # noqa: BLE001 -- one bad review must not abort the sweep
                log.debug("review upsert skipped: %s", e)
    out = {"rating": rating, "review_count": count, "reviews_ingested": ingested,
           "place": place.get("title")}
    log.info("gbp reviews biz %d: %s", business_id, out)
    return out


def latest(business_id: int) -> dict:
    """Current rating snapshot + delta vs the prior snapshot + recent reviews (for the UI/report)."""
    with db() as conn:
        snaps = conn.execute(
            "SELECT rating, review_count, place_name, captured_at FROM gbp_snapshots "
            "WHERE business_id=%s ORDER BY id DESC LIMIT 2", (business_id,)).fetchall()
        # full history for the velocity trendline (oldest -> newest)
        hist = conn.execute(
            "SELECT rating, review_count, captured_at FROM gbp_snapshots "
            "WHERE business_id=%s ORDER BY id", (business_id,)).fetchall()
        reviews = conn.execute(
            "SELECT author, rating, body, sentiment, review_url, discovered_at FROM reviews "
            "WHERE business_id=%s ORDER BY discovered_at DESC LIMIT 12", (business_id,)).fetchall()
    cur = dict(snaps[0]) if snaps else None
    prev = dict(snaps[1]) if len(snaps) > 1 else None
    delta = None
    if cur and prev and cur.get("rating") is not None and prev.get("rating") is not None:
        delta = round(float(cur["rating"]) - float(prev["rating"]), 1)
    return {"current": cur, "rating_delta": delta,
            "new_reviews": (cur["review_count"] - prev["review_count"])
            if (cur and prev and cur.get("review_count") and prev.get("review_count")) else None,
            "history": [{"date": h["captured_at"].date().isoformat() if h["captured_at"] else None,
                         "rating": float(h["rating"]) if h["rating"] is not None else None,
                         "review_count": h["review_count"]} for h in hist],
            "reviews": [dict(r) for r in reviews]}


def main() -> None:
    ap = argparse.ArgumentParser(description="Google review ingestion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("ingest", "show"):
        p = sub.add_parser(c); p.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    print(json.dumps(ingest(args.business_id) if args.cmd == "ingest" else latest(args.business_id),
                     indent=2, default=str))


if __name__ == "__main__":  # pragma: no cover
    main()
