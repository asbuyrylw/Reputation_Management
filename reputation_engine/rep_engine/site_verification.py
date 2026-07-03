"""
Guided Google Search Console verification (onboarding assist)
=============================================================
For clients who don't yet have a VERIFIED Search Console property. Uses the Site Verification
API (getToken -> owner places token -> verify) + Search Console sites.add, all through the
existing GSC OAuth connection.

We deliberately do NOT auto-place the token: the WordPress REST API can't reliably write a
<meta> tag into <head> or a file at the site root, so an "assisted" path would be fragile and
silently fail. Instead we hand the owner the exact token + copy-paste instructions (a <meta>
tag for a URL, or a DNS TXT record for a whole domain), they place it, then we verify and
register the property -- which makes it selectable in the property picker.

Tenant-safe: `vault.credentials(conn_id, business_id)` fails closed on a cross-business id.
Keyless-safe: a missing/expired connection or an unconfigured OAuth client returns a graceful
error dict; nothing here raises for an expected condition.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

try:
    from .connections import vault as _vault
    from .connections.providers import google_search_console as _gsc
except ImportError:  # pragma: no cover -- loose-script fallback
    from connections import vault as _vault  # type: ignore
    from connections.providers import google_search_console as _gsc  # type: ignore

log = logging.getLogger("site_verification")

# Methods we surface in the UI. META -> URL-prefix property; DNS_TXT -> domain property.
METHODS = ("META", "DNS_TXT")


def _identifier_and_property(site_url: str, method: str) -> tuple[str, str]:
    """Derive the Site-Verification `identifier` and the resulting GSC `property` string from a
    user-entered URL/domain + method:
        META    -> identifier "https://example.com/" , property "https://example.com/"
        DNS_TXT -> identifier "example.com"          , property "sc-domain:example.com"
    """
    raw = (site_url or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path).strip("/").lower()
    if method == "DNS_TXT":
        domain = host[4:] if host.startswith("www.") else host
        return domain, f"sc-domain:{domain}"
    url = f"https://{host}/"  # URL-prefix property: force https + a single trailing slash
    return url, url


def _conn(business_id: int, conn_id: int) -> Optional[dict]:
    """Decrypted GSC connection creds, business-scoped, or None when absent/wrong kind."""
    creds = _vault.credentials(conn_id, business_id)
    if not creds or creds.get("kind") != "google_search_console":
        return None
    return creds


def _instructions(method: str, identifier: str) -> str:
    """Human guidance shown alongside the token (the token itself is returned separately)."""
    if method == "DNS_TXT":
        return (f"Add the TXT record below to the DNS for {identifier} (host \"@\"), then click "
                f"Verify. DNS changes can take a few minutes to propagate.")
    return (f"Paste the tag below inside the <head> of {identifier} (the home page is enough), "
            f"publish the change, then click Verify.")


def start(business_id: int, conn_id: int, site_url: str, method: str = "META") -> dict:
    """Step 1: mint a verification token for the chosen method. Returns the token + human
    instructions the owner places on their site/DNS before calling complete()."""
    if method not in METHODS:
        return {"ok": False, "error": f"unsupported method '{method}'"}
    creds = _conn(business_id, conn_id)
    if not creds:
        return {"ok": False, "error": "Search Console connection not found"}
    identifier, prop = _identifier_and_property(site_url, method)
    out = _gsc.get_verification_token(creds.get("access_token") or "", identifier, method=method)
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error") or "could not get a verification token"}
    token = out.get("token") or ""
    return {"ok": True, "method": method, "identifier": identifier, "property": prop,
            "token": token, "instructions": _instructions(method, identifier)}


def complete(business_id: int, conn_id: int, site_url: str, method: str = "META") -> dict:
    """Step 2: verify ownership (token must already be placed) + register the property in Search
    Console. On success the property becomes selectable in the picker. `added` is False (with a
    hint) when ownership verified but sites.add failed -- e.g. the connection predates the
    read-write `webmasters` scope and needs a reconnect."""
    if method not in METHODS:
        return {"ok": False, "error": f"unsupported method '{method}'"}
    creds = _conn(business_id, conn_id)
    if not creds:
        return {"ok": False, "error": "Search Console connection not found"}
    token = creds.get("access_token") or ""
    identifier, prop = _identifier_and_property(site_url, method)
    v = _gsc.verify_site(token, identifier, method=method)
    if not v.get("ok"):
        return {"ok": False, "verified": False,
                "error": v.get("error") or "we couldn't find the verification token yet -- "
                                           "give it a moment after publishing, then retry"}
    added = _gsc.add_site(token, prop)
    return {
        "ok": True, "verified": True, "property": prop, "added": bool(added.get("ok")),
        "add_error": None if added.get("ok") else (
            added.get("error") or "verified, but couldn't auto-add it to Search Console -- "
            "reconnect Search Console to grant access, or add the property in Search Console"),
    }
