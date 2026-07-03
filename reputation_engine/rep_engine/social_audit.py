"""
Own-social discovery + per-platform audit (Phase B)
===================================================
Turns the old boolean "a profile probably exists" guess into a discovered + audited record that the
gap model and plan can act on, DYNAMICALLY per business (driven by businesses.name/domain/geo):

  1. DISCOVER each owned profile the most reliable way first:
       - harvest social links straight off the business website (footer/header) -> OWNED/confirmed,
       - else infer via a budgeted web search                                   -> inferred,
       - Google Business Profile via Serper "places"                            -> confirmed + rich
         signals (rating, review count, categories).
  2. AUDIT each platform: ONE cheap LLM call scores per-platform completeness and produces concrete
     improvement findings + recommendations, grounded in the discovered signals + platform best
     practices. Keyless/dormant-safe: with no LLM key it falls back to a heuristic checklist.
  3. PERSIST into social_presence (exists/url/source/confidence/completeness/audit) so
     social_audit.latest_summary() can ground the gap model's social surface_actions ("improve your
     existing LinkedIn: <fix>" instead of blindly "create one").

Honesty: many platforms (LinkedIn/IG/FB) block scraping, so the audit reasons from what is genuinely
observable (a confirmed owned link, search snippets, GBP data) plus platform best practices -- it
never claims to have read a page it could not fetch.

Run:
    python -m rep_engine.social_audit run --business-id 1
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from urllib.parse import urlparse

try:
    from . import agent_tools as tools
    from . import gbp_reviews as _gbp
    from . import http as _http
    from .ai_state_audit import orchestrator_json
    from .db import db
except ImportError:  # pragma: no cover
    import agent_tools as tools  # type: ignore
    import gbp_reviews as _gbp  # type: ignore
    import http as _http  # type: ignore
    from ai_state_audit import orchestrator_json  # type: ignore
    from db import db  # type: ignore

log = logging.getLogger("social_audit")

# platform -> domains that count as "a profile on that platform"
_PLATFORM_DOMAINS = {
    "linkedin": ["linkedin.com"],
    "facebook": ["facebook.com", "fb.com"],
    "instagram": ["instagram.com"],
    "x": ["x.com", "twitter.com"],
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com"],
    "pinterest": ["pinterest.com"],
    "reddit": ["reddit.com"],
}
# href paths that are share/intent widgets, not the business's own profile
_NON_PROFILE = ("/share", "/sharer", "/intent", "/share_channel", "/dialog/", "sharer.php",
                "/widgets/", "plugins/", "/login", "/signup")
# URL path fragments that mean "a piece of CONTENT" (a post/video/photo), not a profile -- a common
# source of search false positives (e.g. someone else's post that merely mentions the name).
_CONTENT_PATHS = ("/posts/", "/post/", "/status/", "/statuses/", "/reel/", "/reels/", "/p/",
                  "/photo", "/photos/", "/videos/", "/video/", "/watch", "/events/", "/groups/",
                  "/story", "/stories/", "/shorts/")
# path segments that are platform routing prefixes, not the business handle itself
_HANDLE_PREFIXES = {"company", "in", "pub", "pages", "page", "c", "channel", "user", "profile.php"}
_PAGES_TO_HARVEST = ("", "/about", "/about-us", "/contact", "/contact-us")


def _norm_url(domain: str) -> str:
    d = (domain or "").strip()
    if not d:
        return ""
    if "//" not in d:
        d = "https://" + d
    return d.rstrip("/")


def _fetch_html(url: str) -> str:
    """SSRF-guarded GET; returns HTML text or '' on any failure (never raises)."""
    try:
        res = _http.request_json("GET", url, parse_json=False, timeout=15, max_retries=1,
                                 guard_redirects=True)
        return res.text or "" if res.ok else ""
    except Exception:  # noqa: BLE001 -- discovery must never crash the audit
        return ""


def _platform_for(url: str) -> str | None:
    u = url.lower()
    for platform, domains in _PLATFORM_DOMAINS.items():
        if any(d in u for d in domains):
            return platform
    return None


def _harvest_site_links(domain: str) -> dict:
    """Fetch the business homepage (+ about/contact) and pull owned social profile URLs out of the
    markup. A link FROM the business's own site is the strongest, free signal that the profile is
    genuinely theirs. Returns {platform: url} (first plausible profile per platform)."""
    base = _norm_url(domain)
    found: dict = {}
    if not base:
        return found
    seen_html = 0
    for path in _PAGES_TO_HARVEST:
        if len(found) >= len(_PLATFORM_DOMAINS) or seen_html >= 3:
            break
        html = _fetch_html(base + path)
        if not html:
            continue
        seen_html += 1
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
            href = m.group(1)
            if href.startswith("//"):
                href = "https:" + href
            if not href.lower().startswith("http"):
                continue
            platform = _platform_for(href)
            if not platform or platform in found:
                continue
            low = href.lower()
            if any(s in low for s in _NON_PROFILE):
                continue
            found[platform] = href.split("?")[0]
    return found


def _handle_segment(url: str) -> str:
    """The business-handle path segment of a profile URL (skips routing prefixes like
    'company'/'in'/'channel'), used to verify the result is actually THIS business."""
    path = [s for s in urlparse(url).path.split("/") if s]
    for seg in path:
        if seg.lower() in _HANDLE_PREFIXES or seg.startswith("@"):
            continue
        return seg.lstrip("@").lower()
    return ""


def _search_profile(name: str, platform: str, domains: list, name_tokens: list, need: int) -> str | None:
    """Budget-gated web-search inference of a profile URL (used only when the website didn't link it).
    Strict to avoid false positives: rejects CONTENT urls (posts/videos/photos) and requires a
    business-name token to appear in the actual handle, not merely in the result title."""
    try:
        results = tools.web_search(f"{name} {platform}", limit=8)
    except Exception:  # noqa: BLE001
        return None
    for r in results:
        url = (r.get("url") or "")
        low = url.lower()
        if not any(d in low for d in domains):
            continue
        if any(s in low for s in _NON_PROFILE) or any(s in low for s in _CONTENT_PATHS):
            continue  # a share widget or a piece of content, not a profile
        handle = _handle_segment(url)
        if not handle or handle in ("home", "feed", "search", "explore"):
            continue
        # require a real name token IN THE HANDLE (handles vary, so token-substring); this is what
        # rejects "facebook.com/AtlantaPoliceDpt/..." matching on a stray "team" in the title.
        if name_tokens and not any(t in handle for t in name_tokens):
            continue
        return url.split("?")[0]
    return None


def _is_profile_url(url: str, domains: list, name_tokens: list) -> str | None:
    """Return the cleaned profile URL if `url` is a plausible OWNED profile on one of `domains`
    (not a post/video/group, and the handle contains a business-name token), else None."""
    low = url.lower()
    if not any(d in low for d in domains):
        return None
    if any(s in low for s in _NON_PROFILE) or any(s in low for s in _CONTENT_PATHS):
        return None
    handle = _handle_segment(url)
    if not handle or handle in ("home", "feed", "search", "explore", "p"):
        return None
    if name_tokens and not any(t in handle for t in name_tokens):
        return None
    return url.split("?")[0]


def _harvest_audit_citations(business_id: int, name_tokens: list) -> dict:
    """Mine the latest completed audit run's cited sources for the business's OWN social profiles.
    The answer engines often surface a profile our website-harvest + search missed, so this catches
    real profiles (e.g. facebook.com/TheTeamUnstoppable) and avoids false 'create a profile you
    already have' tasks. Same profile/content/handle filtering; best (cleanest) URL per platform."""
    with db() as conn:
        run = conn.execute("SELECT id FROM audit_runs WHERE business_id=%s AND finished_at IS NOT NULL "
                           "ORDER BY id DESC LIMIT 1", (business_id,)).fetchone()
        if not run:
            return {}
        rows = conn.execute("SELECT cited_sources FROM answers WHERE run_id=%s "
                            "AND cited_sources IS NOT NULL", (run["id"],)).fetchall()
    best: dict = {}
    for row in rows:
        for c in (row["cited_sources"] or []):
            url = (c.get("url") if isinstance(c, dict) else str(c)) or ""
            for platform, domains in _PLATFORM_DOMAINS.items():
                clean = _is_profile_url(url, domains, name_tokens)
                if not clean:
                    continue
                # prefer the cleanest profile root (shortest path) per platform
                cur = best.get(platform)
                if cur is None or len(urlparse(clean).path) < len(urlparse(cur).path):
                    best[platform] = clean
    return best


def _gbp_signal(name: str, geo: str) -> dict | None:
    """Google Business Profile via Serper places -> rich completeness signals, or None if unavailable."""
    data = _gbp._serper("places", {"q": f"{name} {geo}".strip(), "gl": "us"})
    places = (data or {}).get("places") or []
    place = _gbp._best_place(places, name) if places else None
    if not place:
        return None
    count = place.get("ratingCount") or place.get("reviewsCount") or place.get("reviews")
    if isinstance(count, list):
        count = len(count)
    return {
        "exists": True, "title": place.get("title"), "rating": place.get("rating"),
        "reviews": count, "category": place.get("category") or place.get("type"),
        "address": place.get("address"), "phone": place.get("phoneNumber"),
        "website": place.get("website"), "cid": place.get("cid") or place.get("placeId"),
    }


def discover(business_id: int) -> dict:
    """Per-platform discovery: {platform: {exists, url, source, confidence, signals}}. Website links
    win (owned), then search (inferred), plus GBP via Serper places."""
    with db() as conn:
        b = conn.execute("SELECT name, domain, geo FROM businesses WHERE id=%s", (business_id,)).fetchone()
    if not b:
        return {}
    name, domain, geo = b["name"], (b.get("domain") or ""), (b.get("geo") or "")
    name_tokens = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) > 2]
    need = max(1, len(name_tokens) // 2) if name_tokens else 0

    harvested = _harvest_site_links(domain)          # owned link from the site = strongest
    cited = _harvest_audit_citations(business_id, name_tokens)  # engine-cited = also strong
    out: dict = {}
    for platform, domains in _PLATFORM_DOMAINS.items():
        if platform in harvested:
            out[platform] = {"exists": True, "url": harvested[platform], "source": "website",
                             "confidence": "verified", "signals": {}}
            continue
        if platform in cited:
            out[platform] = {"exists": True, "url": cited[platform], "source": "citation",
                             "confidence": "verified", "signals": {}}
            continue
        url = None
        if not tools.over_budget(business_id):
            url = _search_profile(name, platform, domains, name_tokens, need)
        out[platform] = {"exists": bool(url), "url": url,
                         "source": "search" if url else "none",
                         "confidence": "inferred" if url else "unknown", "signals": {}}

    gbp = _gbp_signal(name, geo)
    out["gbp"] = ({"exists": True, "url": None, "source": "serper", "confidence": "verified",
                   "signals": gbp} if gbp
                  else {"exists": False, "url": None, "source": "none", "confidence": "unknown",
                        "signals": {}})
    return out


_AUDIT_SYSTEM = (
    "You are a social-media presence auditor for a local/professional business. You are given the "
    "business profile and, per platform, what discovery actually found (whether a profile EXISTS, "
    "its URL, the SOURCE of that finding -- 'website' means the business's own site links to it so it "
    "is confirmed owned; 'search' means inferred; 'serper' is Google Business Profile data -- and any "
    "signals such as GBP rating/review count/category). "
    "For EACH platform return an object: present (bool, from the discovery, do not invent), "
    "completeness (0.0-1.0 estimate of how well-built/active the presence is, conservative when you "
    "only have existence), findings (1-3 concrete observations), recommendations (1-3 specific, "
    "actionable improvements grounded in that platform's best practices AND the discovered signals -- "
    "e.g. for a confirmed GBP with a low review count, 'launch a review-request campaign to reach 50+ "
    "reviews'; for a missing platform that matters for this business, 'create a profile because <why>'; "
    "for a confirmed but likely-thin profile, the specific build-out steps). Do NOT tell them to create "
    "a profile the discovery shows already exists. Prioritize the platforms that matter most for THIS "
    "business type and its goal. "
    "Return STRICT JSON: {\"platforms\": {\"<platform>\": {\"present\": bool, \"completeness\": number, "
    "\"findings\": [..], \"recommendations\": [..]}}, \"summary\": \"2-3 sentences on the overall social "
    "posture and the highest-leverage fix\"}."
)

# Heuristic fallback recommendations when no LLM is configured (keyless/dormant-safe).
_BEST_PRACTICE = {
    "linkedin": "Build out the company page (banner, tagline, services, regular thought-leadership posts) and link it from the website.",
    "facebook": "Complete the Page (about, services, hours, CTA button) and post consistently; pin a credibility post.",
    "instagram": "Use a business account with a clear bio + website link; post a consistent grid (education, client wins).",
    "x": "Post financial-education + local content with relevant hashtags; pin a trust-building thread.",
    "youtube": "Publish short educational videos answering common client questions (great for AI citation + SEO).",
    "tiktok": "Short educational/explainer clips; not required for every B2B niche.",
    "pinterest": "Optional; useful only if you produce visual/infographic content.",
    "reddit": "Engage authentically in local/industry subreddits; do not spam. Monitor for contested threads.",
    "gbp": "Claim/complete the Google Business Profile, add categories, photos, services, and run a review-request campaign.",
}


def _assess(business: dict, discovered: dict) -> dict:
    """One cheap LLM call -> per-platform completeness + findings + recommendations. Falls back to a
    heuristic checklist when the orchestrator is unconfigured, so this is always dormant-safe."""
    payload = json.dumps({"business": {k: business.get(k) for k in ("name", "domain", "services",
                          "goal", "geo")}, "discovered": discovered}, default=str)
    try:
        res = orchestrator_json(_AUDIT_SYSTEM, payload, tier="cheap", max_tokens=2500, timeout=120)
    except Exception as e:  # noqa: BLE001
        log.warning("social audit LLM unavailable (%s); using heuristic fallback", e)
        res = {}
    plats = (res or {}).get("platforms") if isinstance(res, dict) else None
    if not plats:  # heuristic fallback
        plats = {}
        for platform, d in discovered.items():
            present = bool(d.get("exists"))
            rec = (_BEST_PRACTICE.get(platform, "Build out and maintain this profile.") if present
                   else f"No profile found — create one if it fits the business. {_BEST_PRACTICE.get(platform,'')}")
            plats[platform] = {"present": present, "completeness": 0.4 if present else 0.0,
                               "findings": [f"source={d.get('source')}, confidence={d.get('confidence')}"],
                               "recommendations": [rec.strip()]}
        res = {"platforms": plats,
               "summary": "Heuristic social posture (LLM assessment unavailable -- no key configured "
                          "or the monthly budget was reached; discovery is unaffected)."}
    return res


def run(business_id: int, quiet: bool = False) -> dict:
    """Discover + audit owned socials and upsert into social_presence. Idempotent. This is the
    entrypoint the `audit_socials` job calls; running it re-grounds the gap model + plan."""
    discovered = discover(business_id)
    if not discovered:
        return {"skipped": True, "reason": "no business"}
    with db() as conn:
        b = conn.execute("SELECT name, domain, services, goal, geo FROM businesses WHERE id=%s",
                         (business_id,)).fetchone()
    assessment = _assess(dict(b), discovered)
    plats = assessment.get("platforms") or {}
    with db() as conn:
        # No-downgrade guard: a transient discovery miss (Serper hiccup, search returned nothing)
        # must NOT flip a previously-found profile to "not found" -- that would wrongly tell the
        # owner to CREATE a profile they already have. Keep the last good finding when this pass
        # found nothing for a platform.
        prior = {r["platform"]: dict(r) for r in conn.execute(
            'SELECT platform, "exists" AS exists, profile_url, source, confidence FROM '
            "social_presence WHERE business_id=%s", (business_id,)).fetchall()}
        for platform, d in discovered.items():
            if not d.get("exists") and d.get("source") == "none":
                p = prior.get(platform)
                if p and p.get("exists"):
                    d = {**d, "exists": True, "url": p.get("profile_url"),
                         "source": p.get("source"), "confidence": p.get("confidence")}
                    discovered[platform] = d
            a = plats.get(platform) or {}
            comp = a.get("completeness")
            audit = {"findings": a.get("findings") or [], "recommendations": a.get("recommendations") or [],
                     "signals": d.get("signals") or {}}
            conn.execute(
                'INSERT INTO social_presence (business_id, platform, "exists", profile_url, '
                "confidence, source, completeness, audit, last_checked_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                "ON CONFLICT (business_id, platform) DO UPDATE SET "
                '"exists"=EXCLUDED."exists", profile_url=EXCLUDED.profile_url, '
                "confidence=EXCLUDED.confidence, source=EXCLUDED.source, "
                "completeness=EXCLUDED.completeness, audit=EXCLUDED.audit, last_checked_at=now()",
                (business_id, platform, bool(d.get("exists")), d.get("url"), d.get("confidence"),
                 d.get("source"), comp, json.dumps(audit)),
            )
        conn.commit()
    out = {"platforms": {p: {"exists": d.get("exists"), "source": d.get("source"),
                             "url": d.get("url")} for p, d in discovered.items()},
           "summary": assessment.get("summary")}
    if not quiet:
        log.info("social audit for business %d: %s", business_id,
                 {p: d.get("source") for p, d in discovered.items()})
        print(json.dumps(out, indent=2, default=str))
    return out


def latest_summary(business_id: int) -> dict:
    """Compact per-platform read for the gap model: {platform: {exists, url, source, confidence,
    completeness, recommendation}}. Empty dict if never audited (fail-safe for the gap model)."""
    with db() as conn:
        rows = conn.execute(
            'SELECT platform, "exists" AS exists, profile_url, source, confidence, completeness, audit '
            "FROM social_presence WHERE business_id=%s", (business_id,),
        ).fetchall()
    out: dict = {}
    for r in rows:
        audit = r["audit"] if isinstance(r["audit"], dict) else (json.loads(r["audit"]) if r["audit"] else {})
        recs = audit.get("recommendations") or []
        out[r["platform"]] = {
            "exists": r["exists"], "url": r["profile_url"], "source": r["source"],
            "confidence": r["confidence"],
            "completeness": float(r["completeness"]) if r["completeness"] is not None else None,
            "recommendation": recs[0] if recs else None,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Own-social discovery + per-platform audit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--business-id", type=int, required=True)
    s = sub.add_parser("summary"); s.add_argument("--business-id", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.business_id)
    elif args.cmd == "summary":
        print(json.dumps(latest_summary(args.business_id), indent=2, default=str))


if __name__ == "__main__":
    main()
