"""Social-presence verification (Phase 7).

Best-effort check of whether a business actually HAS a profile on each platform, so the
"recommended social presence" items can move from unverified suggestions toward a confirmed
"create a profile" vs "improve the existing one". Search-based inference (via the budgeted web
search), so confidence is 'inferred', never asserted as ground truth -- the UI labels it honestly.
"""

from __future__ import annotations

import logging
import re

try:
    from . import agent_tools as tools
    from .db import db
except ImportError:  # pragma: no cover
    import agent_tools as tools  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("social_presence")

# platform -> the domains that count as "a profile on that platform"
_PLATFORM_DOMAINS = {
    "linkedin": ["linkedin.com"],
    "x": ["x.com", "twitter.com"],
    "facebook": ["facebook.com"],
    "instagram": ["instagram.com"],
    "reddit": ["reddit.com"],
}


def verify(business_id: int, quiet: bool = False) -> dict:
    """For each platform, search for the business and see if a matching profile URL turns up.
    Stores the result in social_presence (upsert). Budget-gated; never fabricates a URL."""
    with db() as conn:
        b = conn.execute("SELECT name FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not b:
        return {"skipped": True, "reason": "no business"}
    name = b["name"]
    # significant name tokens, to require the result is plausibly THIS business (not a same-named
    # other) before we call a profile "found".
    name_tokens = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) > 2]
    need = max(1, len(name_tokens) // 2) if name_tokens else 0
    out: dict = {}
    for platform, domains in _PLATFORM_DOMAINS.items():
        if tools.over_budget(business_id):
            break
        try:
            results = tools.web_search(f"{name} {platform}", limit=8)
        except Exception:  # noqa: BLE001 -- a failed search must not abort the sweep
            results = []
        found_url = None
        for r in results:
            url = (r.get("url") or "").lower()
            title = (r.get("title") or "").lower()
            if not any(d in url for d in domains):
                continue
            # the profile URL is on the right platform; also require the business name to appear
            hay = f"{url} {title}"
            if need and sum(1 for t in name_tokens if t in hay) < need:
                continue  # likely a different, same-named entity -> don't claim it as "found"
            found_url = r.get("url")
            break
        exists = found_url is not None
        with db() as conn:
            conn.execute(
                'INSERT INTO social_presence (business_id, platform, "exists", profile_url, '
                "confidence, last_checked_at) VALUES (%s,%s,%s,%s,'inferred',now()) "
                "ON CONFLICT (business_id, platform) DO UPDATE SET "
                '"exists"=EXCLUDED."exists", profile_url=EXCLUDED.profile_url, '
                "confidence='inferred', last_checked_at=now()",
                (business_id, platform, exists, found_url),
            )
            conn.commit()
        out[platform] = {"exists": exists, "profile_url": found_url}
    if not quiet:
        log.info("social presence for business %d: %s", business_id,
                 {k: v["exists"] for k, v in out.items()})
    return out


def latest(business_id: int) -> dict:
    """Latest verification per platform: {platform: {exists, profile_url, confidence, last_checked_at}}."""
    with db() as conn:
        rows = conn.execute(
            'SELECT platform, "exists" AS exists, profile_url, confidence, last_checked_at '
            "FROM social_presence WHERE business_id=%s",
            (business_id,),
        ).fetchall()
    return {r["platform"]: dict(r) for r in rows}
