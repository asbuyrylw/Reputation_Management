"""
Reputation Crowding-Out Engine -- review-request loop + GBP NAP (LATER)
======================================================================
Closes the review-capture loop the product recommends but never operationalized: a ready-to-send
"please review us" link + message templates (SMS/email), plus a canonical NAP (Name / Address /
Phone) block for citation consistency -- the single highest-leverage local-SEO + AI-sentiment
asset for a local firm. Read-only + keyless: builds the best link it can from the Google place
snapshot (cid) we already ingest, falling back to a Google search link.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote_plus

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore


def _latest_place(business_id: int) -> dict:
    with db() as conn:
        r = conn.execute(
            "SELECT cid, place_name FROM gbp_snapshots WHERE business_id=%s "
            "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
    return dict(r) if r else {}


def review_link(business_id: int) -> dict:
    """Best-effort 'write a review' link + the listing link. Uses the Google `cid` from the latest
    snapshot when available, else a Google-search fallback that always works."""
    with db() as conn:
        b = conn.execute("SELECT name, geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
    name = (b or {}).get("name") or ""
    geo = (b or {}).get("geo") or ""
    place = _latest_place(business_id)
    cid = place.get("cid")
    if cid:
        write_url = f"https://search.google.com/local/writereview?placeid={quote_plus(str(cid))}"
        listing_url = f"https://www.google.com/maps?cid={quote_plus(str(cid))}"
        source = "google_place_cid"
    else:
        q = quote_plus(f"{name} {geo} reviews".strip())
        write_url = f"https://www.google.com/search?q={q}"
        listing_url = write_url
        source = "search_fallback"
    return {"write_review_url": write_url, "listing_url": listing_url, "source": source,
            "place_name": place.get("place_name") or name}


def templates(business_id: int) -> dict:
    """Short, compliant request templates (the link is substituted client-side)."""
    with db() as conn:
        b = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
    name = (b or {}).get("name") or "us"
    link = review_link(business_id)["write_review_url"]
    sms = (f"Hi {{first_name}}, thanks for choosing {name}! If we earned it, a quick Google review "
           f"would mean a lot: {link}")
    email_subject = f"Would you share your experience with {name}?"
    email_body = (f"Hi {{first_name}},\n\nThank you for trusting {name}. If you have a moment, a short "
                  f"Google review helps others find us and tells us how we did:\n{link}\n\n"
                  f"We appreciate you.\n— The {name} team")
    return {"sms": sms, "email_subject": email_subject, "email_body": email_body, "link": link}


def nap(business_id: int) -> dict:
    """Canonical Name/Address/Phone block for citation consistency (NAP). Flags missing fields the
    owner should fill in, since NAP mismatches across directories suppress local rank."""
    sql = ("SELECT name, geo, domain, phone, address FROM businesses WHERE id=%s" if _has_cols()
           else "SELECT name, geo, domain FROM businesses WHERE id=%s")
    with db() as conn:
        b = conn.execute(sql, (business_id,)).fetchone()
    b = dict(b) if b else {}
    missing = [f for f in ("name", "phone", "address") if not b.get(f)]
    return {"name": b.get("name"), "address": b.get("address"), "phone": b.get("phone"),
            "website": b.get("domain"), "areas_served": b.get("geo"),
            "missing_fields": missing,
            "consistency_note": ("Keep this exact NAP identical across Google, your website, and every "
                                 "directory -- mismatches split your local authority.")}


def _has_cols() -> bool:
    """businesses may not have phone/address columns on older schemas -- detect once."""
    try:
        with db() as conn:
            n = conn.execute(
                "SELECT count(*) n FROM information_schema.columns WHERE table_name='businesses' "
                "AND column_name IN ('phone','address')").fetchone()["n"]
        return n >= 2
    except Exception:  # noqa: BLE001
        return False
