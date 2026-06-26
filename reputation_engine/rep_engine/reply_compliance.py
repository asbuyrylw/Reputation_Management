"""
Reputation Crowding-Out Engine -- deterministic FTC reply screen (Integrations Phase 0)
=======================================================================================
Brand replies to reviews / mentions carry FTC + platform-ToS risk that the generic
financial-marketing screener (`content_generator.COMPLIANCE_SYSTEM`) does NOT catch,
because that screen *passes* anything "non-financial or purely informational" -- which a
review reply almost always is. Left to the LLM screen alone, every reply would auto-pass.

This module is the non-injectable, deterministic backstop the design requires: it runs on
EVERY reply path (`_compliance(..., is_reply=True)`), and a hit is AUTHORITATIVE -> the reply
is forced `pass=False` (manual) regardless of the LLM verdict. Until this screen is wired in,
every reply path is forced `manual`.

The three regulated failure modes (16 CFR Part 465 "fake reviews/testimonials" + platform ToS):
  1. First-person-customer voice  -- a brand reply must speak AS the business, never pose as a
     customer/reviewer ("As a customer, I ...", "I bought ...", "I visited ...").
  2. Review solicitation / incentive -- a reply must not ask for a review or dangle a reward
     ("leave us a review", "in exchange for", "discount for a review", "we'll comp you").
  3. Impersonation -- a reply must not claim to be a platform/official ("Google verified team",
     "official Yelp representative") or sign as the reviewer.

Pure stdlib, no LLM, no network -- safe to call in any path including a request.
"""

from __future__ import annotations

import re
from typing import Optional

# --- First-person-customer voice ------------------------------------------------------------
# A brand reply legitimately says "we"/"our team". It must NOT narrate a customer experience in
# the first person. We flag explicit customer self-identification and first-person consumption
# verbs that only a reviewer (not the business) would write.
_FIRST_PERSON_CUSTOMER = [
    (r"\bas a (?:customer|client|patient|guest|reviewer)\b", "first-person-customer voice ('as a customer ...')"),
    (r"\bI (?:bought|purchased|ordered|used|tried|visited|hired|signed up|booked|stayed)\b",
     "first-person customer experience ('I bought/used/visited ...')"),
    (r"\b(?:I|we) (?:gave|left|wrote) (?:them|this place|you) (?:a|\d)\b[^.\n]{0,20}\b(?:star|review)\b",
     "reply poses as the reviewer ('I gave them 5 stars')"),
    (r"\bmy experience as (?:a|their) (?:customer|client|patient)\b", "first-person-customer framing"),
]

# --- Review solicitation / incentive --------------------------------------------------------
_SOLICITATION = [
    (r"\bleave (?:us |me )?(?:a |an )?(?:\d[-\s]?star )?review\b", "solicits a review"),
    (r"\b(?:write|post|give) (?:us |me )?(?:a |an )?(?:\d[-\s]?star )?review\b", "solicits a review"),
    (r"\bin exchange for (?:a |your )?(?:review|rating|feedback|testimonial)\b", "incentivized review (quid-pro-quo)"),
    (r"\b(?:discount|coupon|gift\s?card|free|comp(?:ed|limentary)?|refund|credit)\b[^.\n]{0,40}\b(?:review|rating|testimonial)\b",
     "offers an incentive for a review"),
    (r"\b(?:review|rating|testimonial)\b[^.\n]{0,40}\b(?:discount|coupon|gift\s?card|free|comp(?:ed|limentary)?|refund|credit)\b",
     "offers an incentive for a review"),
    (r"\b(?:update|change|revise|remove|take down) your (?:review|rating|star)\b",
     "asks the reviewer to alter/remove their review"),
]

# --- Impersonation --------------------------------------------------------------------------
_IMPERSONATION = [
    (r"\b(?:official|verified) (?:google|yelp|facebook|meta|trustpilot|bbb)\b[^.\n]{0,20}\b(?:team|representative|rep|support|staff)\b",
     "impersonates a platform/official representative"),
    (r"\bon behalf of (?:google|yelp|facebook|meta|trustpilot|bbb)\b",
     "claims to act on the platform's behalf"),
    (r"\bthis is (?:google|yelp|facebook|meta) (?:support|trust|safety)\b", "impersonates platform support"),
]

_ALL_RULES = [
    *( (re.compile(p, re.I), m) for p, m in _FIRST_PERSON_CUSTOMER),
    *( (re.compile(p, re.I), m) for p, m in _SOLICITATION),
    *( (re.compile(p, re.I), m) for p, m in _IMPERSONATION),
]


def screen(text: Optional[str]) -> list[str]:
    """Return the list of triggered FTC/ToS reply-rule descriptions (empty == clean).

    Deterministic and non-injectable: a hit is authoritative. Callers (`_compliance` with
    ``is_reply=True``) merge these into `flags` and force `pass=False`."""
    body = text or ""
    seen: list[str] = []
    for pat, msg in _ALL_RULES:
        if pat.search(body) and msg not in seen:
            seen.append(msg)
    return seen


# Reply-specific LLM screen system prompt. Unlike COMPLIANCE_SYSTEM (which passes anything
# "non-financial"), this prompt knows it is screening a BRAND REPLY and must not rubber-stamp it.
REPLY_COMPLIANCE_SYSTEM = (
    "You are screening a BUSINESS's public reply to a customer review or online mention before it "
    "is posted under the business's name. Return STRICT JSON only: {\"pass\": bool, \"flags\": [strings]}. "
    "This is NOT marketing copy -- do not pass it merely because it is 'non-financial'. Flag any of: "
    "the reply speaks in a customer's first-person voice instead of the business's voice; it solicits, "
    "incentivizes, or asks to alter a review (16 CFR Part 465); it impersonates a platform or official; "
    "it discloses private customer information (full name + account/order/health details); it is hostile, "
    "defamatory, or makes a legal admission; for a financial firm, it makes a performance/return promise "
    "or a guarantee. A professional, on-brand, factual reply that thanks the reviewer and offers to make "
    "things right should pass."
)
