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


def send(business_id: int, recipients: list[dict]) -> dict:
    """Send review-requests (Wave 4, item 15) over BOTH channels, each dormant-safe:
      - email via email_service (SMTP), and
      - SMS / GoHighLevel via the webhook bus -- each recipient is emitted as a 'review_request'
        event carrying email + phone + the SMS template + link, so a GHL/Zapier workflow can text it.
    Each recipient is {email?, phone?, first_name?}. If NEITHER channel is configured it returns a
    preview (skipped=True) rather than failing. New-review impact is read from the gbp_snapshots
    count delta."""
    try:
        from . import email_service as _es
    except ImportError:  # pragma: no cover
        import email_service as _es  # type: ignore
    try:
        from . import webhooks as _wh
    except ImportError:  # pragma: no cover
        import webhooks as _wh  # type: ignore
    tpl = templates(business_id)
    email_on, ghl_on = _es.enabled(), _wh.enabled(business_id)
    if not email_on and not ghl_on:
        return {"sent": 0, "skipped": True,
                "reason": "no review-request channel configured (set SMTP_* for email or a tenant webhook "
                          "for SMS/GoHighLevel)",
                "preview": {"subject": tpl["email_subject"], "body": tpl["email_body"], "sms": tpl["sms"]}}
    sent = failed = ghl = 0
    for r in recipients or []:
        first = (r.get("first_name") or "there").strip()
        to = (r.get("email") or "").strip()
        if email_on and to:
            try:
                ok = _es.send_email(to, tpl["email_subject"], tpl["email_body"].replace("{first_name}", first))
                sent += 1 if ok else 0
                failed += 0 if ok else 1
            except Exception:  # noqa: BLE001
                failed += 1
        if ghl_on and (r.get("phone") or to):
            try:  # hand off to GHL/Zapier for the SMS (or its own email workflow)
                _wh.emit(business_id, "review_request", {
                    "email": to, "phone": (r.get("phone") or "").strip(), "first_name": first,
                    "sms": tpl["sms"].replace("{first_name}", first), "link": tpl["link"]})
                ghl += 1
            except Exception:  # noqa: BLE001
                pass
    return {"sent": sent, "failed": failed, "ghl_fanout": ghl}


def _format_location_address(loc: dict) -> str:
    """Compose a single-line address string from a structured locations row."""
    street = (loc.get("address") or "").strip()
    region = " ".join(p for p in [(loc.get("state") or "").strip(), (loc.get("postal") or "").strip()] if p)
    tail = ", ".join(p for p in [(loc.get("city") or "").strip(), region] if p)
    return ", ".join(p for p in [street, tail] if p)


def nap(business_id: int) -> dict:
    """Canonical Name/Address/Phone block for citation consistency (NAP). Flags missing fields the
    owner should fill in, since NAP mismatches across directories suppress local rank. Address/phone
    fall back to the business's PRIMARY structured location when the businesses.{address,phone} columns
    are empty -- that's where the owner actually enters them -- so the NAP isn't shown as 'Missing'
    when the data already exists on the location record."""
    sql = ("SELECT name, geo, domain, phone, address FROM businesses WHERE id=%s" if _has_cols()
           else "SELECT name, geo, domain FROM businesses WHERE id=%s")
    with db() as conn:
        b = conn.execute(sql, (business_id,)).fetchone()
        b = dict(b) if b else {}
        address = (b.get("address") or "").strip()
        phone = (b.get("phone") or "").strip()
        if not address or not phone:
            try:
                loc = conn.execute(
                    "SELECT address, city, state, postal, phone FROM locations "
                    "WHERE business_id=%s ORDER BY is_primary DESC, id LIMIT 1", (business_id,)).fetchone()
            except Exception:  # noqa: BLE001 -- locations table may not exist on older schemas
                loc = None
            if loc:
                loc = dict(loc)
                if not phone:
                    phone = (loc.get("phone") or "").strip()
                if not address:
                    address = _format_location_address(loc)
    name = (b.get("name") or "").strip()
    missing = [k for k, v in (("name", name), ("phone", phone), ("address", address)) if not v]
    return {"name": b.get("name"), "address": address or None, "phone": phone or None,
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
