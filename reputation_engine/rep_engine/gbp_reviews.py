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
    # Serper returns the review count under varying keys; `reviews` is sometimes a list of review
    # objects -> use its length in that case rather than silently dropping the count.
    count = place.get("ratingCount") or place.get("reviewsCount") or place.get("reviews")
    if isinstance(count, list):
        count = len(count)
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
    # Draft brand replies for any new reviews + queue them for human approval (Phase 3).
    drafted = 0
    try:
        drafted = _draft_pending(business_id)
    except Exception as e:  # noqa: BLE001 -- drafting must not abort ingest
        log.debug("review reply drafting skipped: %s", e)
    out = {"rating": rating, "review_count": count, "reviews_ingested": ingested,
           "replies_drafted": drafted, "place": place.get("title")}
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


# ============================================================================
# Reply path (Integrations Phase 3): draft -> human approve -> post -> reconcile
# ============================================================================
GBP_BASE = os.getenv("GBP_API_BASE", "https://mybusiness.googleapis.com/v4")

REVIEW_SYSTEM = (
    "You write a SHORT, warm, professional reply from a business to a customer's Google review. "
    "Speak in the business's voice ('we'/'our team'), never as a customer. Thank the reviewer, "
    "acknowledge specifics, and for a negative review apologize briefly and invite them to make it "
    "right offline -- WITHOUT admitting fault, disclosing private details, or making promises. Do "
    "NOT solicit reviews or offer incentives. 2-4 sentences. Output only the reply text."
)


def _fence(text) -> str:
    try:
        from .ai_state_audit import _fence_untrusted
    except ImportError:  # pragma: no cover
        from ai_state_audit import _fence_untrusted  # type: ignore
    return _fence_untrusted(text)


def _cg():
    try:
        from . import content_generator as cg
    except ImportError:  # pragma: no cover
        import content_generator as cg  # type: ignore
    return cg


def _redact_author(business_id: int, review_id: int, author: Optional[str]) -> None:
    """GDPR: once a reply is drafted the brand reply needs no author identity -- replace it with a
    stable hash and flag it redacted."""
    h = "reviewer-" + hashlib.sha256(f"{business_id}|{author or ''}".encode()).hexdigest()[:10]
    with db() as conn:
        conn.execute("UPDATE reviews SET author=%s, author_pii_redacted=TRUE WHERE id=%s",
                     (h, review_id))
        conn.commit()


def _auto_reply_ok(settings, rating, sentiment, body, draft, comp) -> bool:
    """The (opt-in) owned-review auto-reply gate. Default-OFF: every condition must hold, including
    the platform kill switch. Negative/rating-only/placeholder/over-long replies never auto-post."""
    try:
        from .integration_flags import autopost_global_enabled
    except ImportError:  # pragma: no cover
        from integration_flags import autopost_global_enabled  # type: ignore
    return bool(
        settings.auto_reply_reviews
        and autopost_global_enabled()
        and comp.get("pass") is True
        and rating is not None and float(rating) >= settings.auto_reply_min_stars
        and sentiment != "negative"
        and bool(body)                       # require a real comment, not a rating-only review
        and bool(draft) and not draft.startswith("[DRAFT")
        and "[INSERT:" not in draft
        and len(draft) <= settings.auto_reply_max_len)


def _draft_pending(business_id: int, limit: int = 20) -> int:
    """Draft a brand reply for each new review, screen it (reply-aware), queue it, and redact author
    PII. Default = pending_review (HUMAN approval). Only a fully-gated, clean, positive review is
    queued auto_posted_pending (the post drain posts it); everything else needs a human."""
    cg = _cg()
    try:
        from . import response_policy as rp
    except ImportError:  # pragma: no cover
        import response_policy as rp  # type: ignore
    settings = rp._settings(business_id)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, author, title, body, rating, sentiment FROM reviews "
            "WHERE business_id=%s AND status='new' ORDER BY id DESC LIMIT %s",
            (business_id, limit)).fetchall()
    drafted = 0
    for r in rows:
        payload = {"rating": r.get("rating"), "sentiment": r.get("sentiment"),
                   "review_title": _fence(r.get("title")), "review_text": _fence(r.get("body"))}
        draft = cg.draft_reply(REVIEW_SYSTEM, payload, max_tokens=300,
                               fallback="[DRAFT unavailable -- write a brief thank-you reply]")
        comp = cg._compliance(draft or "", is_reply=True)
        auto = _auto_reply_ok(settings, r.get("rating"), r.get("sentiment"), r.get("body"), draft, comp)
        init_status = "auto_posted_pending" if auto else "pending_review"
        try:
            with db() as conn:
                ins = conn.execute(
                    "INSERT INTO review_replies (review_id, business_id, draft, compliance_pass, "
                    "compliance_flags, status, reviewer, auto_generated) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE) "
                    "ON CONFLICT (review_id) WHERE status NOT IN ('rejected','failed','superseded') "
                    "DO NOTHING RETURNING id",
                    (r["id"], business_id, draft, comp.get("pass"),
                     json.dumps(comp.get("flags") or []), init_status,
                     "auto" if auto else None)).fetchone()
                if ins:
                    conn.execute("UPDATE reviews SET status='drafted' WHERE id=%s", (r["id"],))
                conn.commit()
        except Exception as e:  # noqa: BLE001
            log.debug("review reply draft skipped for %s: %s", r["id"], e)
            continue
        if ins:  # only count + redact when a NEW reply was actually queued (idempotent re-run)
            drafted += 1
            _redact_author(business_id, r["id"], r.get("author"))
    return drafted


def _gbp_connection(business_id: int) -> Optional[dict]:
    """Resolve an active, allowlist-approved Google Business Profile connection, or None."""
    try:
        from .connections import vault
    except ImportError:  # pragma: no cover
        from connections import vault  # type: ignore
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM platform_connections WHERE business_id=%s AND kind='google_business_profile' "
            "AND status='active' AND gbp_access='approved' ORDER BY id DESC LIMIT 1",
            (business_id,)).fetchone()
    if not row:
        return None
    return vault.credentials(row["id"], business_id)


def list_review_replies(business_id: int, status_filter: Optional[str] = None) -> list[dict]:
    where = "rr.business_id=%s" + (" AND rr.status=%s" if status_filter else "")
    params = (business_id, status_filter) if status_filter else (business_id,)
    with db() as conn:
        rows = conn.execute(
            "SELECT rr.id, rr.review_id, rr.draft, rr.compliance_pass, rr.compliance_flags, "
            "rr.status, rr.reviewer, rr.reviewed_at, rr.posted_at, rr.external_url, rr.created_at, "
            "rv.author, rv.rating, rv.title AS review_title, rv.body AS review_body, "
            "rv.sentiment, rv.review_url "
            "FROM review_replies rr JOIN reviews rv ON rv.id=rr.review_id "
            f"WHERE {where} ORDER BY rr.id DESC", params).fetchall()
    return [dict(r) for r in rows]


def approve_reply(reply_id: int, reviewer: str, business_id: int) -> bool:
    """Human approve -> 'approved' (the post_review_replies drain posts it). Business-scoped.
    Refuses a reply that FAILED the compliance screen (compliance_pass IS FALSE) -- it must be
    edited (which re-screens) first. Raises ValueError on a hard-fail so the router can 422."""
    with db() as conn:
        row = conn.execute(
            "SELECT compliance_pass FROM review_replies WHERE id=%s AND business_id=%s AND "
            "status='pending_review' FOR UPDATE", (reply_id, business_id)).fetchone()
        if not row:
            conn.commit()
            return False
        if row["compliance_pass"] is False:
            conn.commit()
            raise ValueError("This reply failed the compliance screen. Edit it to resolve the "
                             "issues (which re-screens it), then approve.")
        conn.execute(
            "UPDATE review_replies SET status='approved', reviewer=%s, reviewed_at=now() "
            "WHERE id=%s AND business_id=%s", (reviewer, reply_id, business_id))
        conn.commit()
    return True


def reject_reply(reply_id: int, reviewer: str, business_id: int) -> bool:
    with db() as conn:
        row = conn.execute(
            "UPDATE review_replies SET status='rejected', reviewer=%s, reviewed_at=now() "
            "WHERE id=%s AND business_id=%s AND status IN ('pending_review','approved') RETURNING id",
            (reviewer, reply_id, business_id)).fetchone()
        conn.commit()
    return bool(row)


def edit_reply(reply_id: int, new_draft: str, editor: str, business_id: int) -> bool:
    """Edit a queued reply: re-screen (reply-aware), reset compliance_pass (never to True), and
    append to the FTC edit trail. Stays pending_review."""
    cg = _cg()
    comp = cg._compliance(new_draft or "", is_reply=True)
    # editing resets to False (hard hit) or None (unscreened) -- never auto-True
    new_pass = False if comp.get("pass") is False else None
    with db() as conn:
        prev = conn.execute(
            "SELECT draft FROM review_replies WHERE id=%s AND business_id=%s AND "
            "status IN ('pending_review','approved') FOR UPDATE", (reply_id, business_id)).fetchone()
        if not prev:
            conn.commit()
            return False
        conn.execute(
            "UPDATE review_replies SET draft=%s, compliance_pass=%s, compliance_flags=%s, "
            "status='pending_review', edits = edits || %s::jsonb WHERE id=%s AND business_id=%s",
            (new_draft, new_pass, json.dumps(comp.get("flags") or []),
             json.dumps([{"by": editor, "prev_text": prev["draft"]}]), reply_id, business_id))
        conn.commit()
    return True


def post_approved(business_id: int) -> dict:
    """Drain approved/auto_posted_pending review replies. Posts via the GBP reply API when an
    allowlist-approved connection exists; otherwise leaves them approved (human posts manually).
    Keyless-safe: a no-connection drain is a clean no-op."""
    try:
        from . import http as _h
    except ImportError:  # pragma: no cover
        import http as _h  # type: ignore
    creds = _gbp_connection(business_id)
    posted = skipped = failed = 0
    with db() as conn:
        rows = conn.execute(
            "SELECT rr.id, rr.draft, rr.status, rr.compliance_pass, rv.external_id, rv.location_ref "
            "FROM review_replies rr JOIN reviews rv ON rv.id=rr.review_id "
            "WHERE rr.business_id=%s AND rr.status IN ('approved','auto_posted_pending')",
            (business_id,)).fetchall()
    for r in rows:
        if r.get("compliance_pass") is False:
            # Should not happen (approve refuses False), but fail safe: degrade to human review
            # rather than retrying a non-compliant reply on every drain.
            _degrade_reply(business_id, r["id"], "reply failed compliance -- returned for human review")
            failed += 1
            continue
        if not creds or not r.get("external_id") or not r.get("location_ref"):
            skipped += 1  # can't post without a live GBP connection + GBP-format ids
            continue
        account = creds.get("account_ref") or ""
        name = f"{account}/{r['location_ref']}/reviews/{r['external_id']}".lstrip("/")
        res = _h.request_json("PUT", f"{GBP_BASE}/{name}/reply",
                              headers={"Authorization": f"Bearer {creds.get('access_token')}",
                                       "Content-Type": "application/json"},
                              json={"comment": r["draft"]}, timeout=20, max_retries=2,
                              guard_redirects=True)
        if res.ok:
            _mark_posted(business_id, r["id"], res.data, auto=(r["status"] == "auto_posted_pending"))
            posted += 1
        elif res.status in (401, 403):
            _degrade_reply(business_id, r["id"], "authorization rejected -- reconnect Google")
            failed += 1
        else:
            _degrade_reply(business_id, r["id"], res.error)
            failed += 1
    return {"posted": posted, "skipped": skipped, "failed": failed}


def _mark_posted(business_id: int, reply_id: int, ack, auto: bool) -> None:
    try:
        from .integration_flags import redact
    except ImportError:  # pragma: no cover
        from integration_flags import redact  # type: ignore
    with db() as conn:
        conn.execute(
            "UPDATE review_replies SET status=%s, posted_at=now(), external_ack=%s, "
            "reviewer=COALESCE(reviewer, %s) WHERE id=%s AND business_id=%s",
            ("auto_posted" if auto else "posted", json.dumps(redact(ack) if ack else {}),
             "auto" if auto else None, reply_id, business_id))
        conn.execute("UPDATE reviews SET status='replied' WHERE id=(SELECT review_id FROM "
                     "review_replies WHERE id=%s)", (reply_id,))
        conn.commit()


def _degrade_reply(business_id: int, reply_id: int, error: Optional[str]) -> None:
    """A failed post degrades back to pending_review (human safety net) with a redacted error."""
    try:
        from .integration_flags import redact
    except ImportError:  # pragma: no cover
        from integration_flags import redact  # type: ignore
    with db() as conn:
        conn.execute(
            "UPDATE review_replies SET status='pending_review', last_error=%s WHERE id=%s AND business_id=%s",
            (redact(error), reply_id, business_id))
        conn.commit()


def reconcile(business_id: int) -> dict:
    """Soft-delete reviews whose source content has clearly gone stale (excluded from auto-reply),
    and ensure any replied reviews have their author PII redacted. Lightweight v1 reconcile."""
    with db() as conn:
        gone = conn.execute(
            "UPDATE reviews SET status='gone' WHERE business_id=%s AND status IN ('new','drafted') "
            "AND last_seen_at < now() - interval '60 days' RETURNING id", (business_id,)).fetchall()
        conn.execute(
            "UPDATE reviews SET author='reviewer-redacted', author_pii_redacted=TRUE "
            "WHERE business_id=%s AND status='replied' AND author_pii_redacted=FALSE", (business_id,))
        conn.commit()
    return {"gone": len(gone)}


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
