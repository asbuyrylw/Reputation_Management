"""
Reputation Crowding-Out Engine -- curated directory & citation automation (Wave 3, item 12; WHITE-HAT)
=====================================================================================================
A VETTED, hand-curated list of high-authority business directories + citation sites (the legitimate
kind that build local authority + NAP consistency) -- NOT auto-backlink farms. Each is surfaced in
the Outreach tab pre-filled with the business's canonical NAP, so a human can submit in one click.
Reuses review_requests.nap for the canonical Name/Address/Phone block.

Curated from the public "awesome-seo-backlinks" / open-startup directory lists, filtered to
high-authority, free, human-submittable destinations. Financial-services-relevant entries flagged.
"""

from __future__ import annotations

from typing import Optional

# (key, name, submit_url, authority, category, financial_relevant)
_DIRECTORIES = [
    ("google_business", "Google Business Profile", "https://www.google.com/business/", "essential", "maps", False),
    ("bing_places", "Bing Places for Business", "https://www.bingplaces.com/", "high", "maps", False),
    ("apple_maps", "Apple Business Connect", "https://businessconnect.apple.com/", "high", "maps", False),
    ("yelp", "Yelp for Business", "https://biz.yelp.com/", "high", "reviews", False),
    ("bbb", "Better Business Bureau", "https://www.bbb.org/get-listed", "high", "trust", True),
    ("facebook_page", "Facebook Business Page", "https://www.facebook.com/business/pages", "high", "social", False),
    ("linkedin_company", "LinkedIn Company Page", "https://www.linkedin.com/company/setup/new/", "high", "social", False),
    ("nextdoor", "Nextdoor Business", "https://business.nextdoor.com/", "medium", "local", False),
    ("yellowpages", "YellowPages", "https://www.yellowpages.com/", "medium", "directory", False),
    ("chamber", "Local Chamber of Commerce", "", "medium", "local", False),
    ("brokercheck", "FINRA BrokerCheck", "https://brokercheck.finra.org/", "essential", "regulatory", True),
    ("adviserinfo", "SEC Investment Adviser Public Disclosure", "https://adviserinfo.sec.gov/", "essential", "regulatory", True),
    ("napfa", "NAPFA Advisor Directory", "https://www.napfa.org/", "high", "industry", True),
    ("xy_planning", "XY Planning Network", "https://www.xyplanningnetwork.com/", "medium", "industry", True),
]


def _is_financial(business_id: int) -> bool:
    try:
        from .db import db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    try:
        with db() as conn:
            r = conn.execute("SELECT regulatory_profile FROM businesses WHERE id=%s", (business_id,)).fetchone()
        ft = ((r or {}).get("regulatory_profile") or {}).get("firm_type") if r else None
        return (ft or "").lower() in ("ria", "broker_dealer", "insurance")
    except Exception:  # noqa: BLE001
        return False


def recommend(business_id: int) -> dict:
    """Return the curated directories relevant to this business, each with the pre-filled NAP for a
    human-approved submission. Financial-only entries are included only for financial firms."""
    try:
        from . import review_requests as _rr
    except ImportError:  # pragma: no cover
        import review_requests as _rr  # type: ignore
    nap = _rr.nap(business_id)
    financial = _is_financial(business_id)
    items = []
    for key, name, url, authority, category, fin in _DIRECTORIES:
        if fin and not financial:
            continue
        items.append({"key": key, "name": name, "submit_url": url, "authority": authority,
                      "category": category, "financial": fin})
    return {"nap": nap, "directories": items,
            "note": "Submit each with the EXACT same NAP shown — consistent citations build local "
                    "authority; mismatches split it. Each submission is human-reviewed.",
            "summary": {"total": len(items), "essential": sum(1 for i in items if i["authority"] == "essential")}}
