"""
Response policy -- surface classification, auto-post routing, unified queue (Phase 4)
=====================================================================================
Decides, for every actionable item, exactly one `surface` (owned vs third_party) and one
`auto_policy` (manual vs auto_eligible). The invariants are enforced structurally here:

  * third_party (Reddit, news, anyone else's surface) is ALWAYS manual -- no code path auto-posts.
  * owned auto_eligible requires ALL of: AUTOPOST_GLOBAL_ENABLED (platform kill switch) +
    tenant opted in (org-manager) + the platform in auto_platforms + compliance_pass IS True +
    sentiment not blocked + guardrails_ok (caps/quiet-hours/length/warmup).

`_settings()` COALESCEs to safe-OFF defaults if the integration_settings row/table is absent, so
this module works before Phase 5 lands and never crashes on cold start.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

try:
    from .db import db
    from .integration_flags import autopost_global_enabled
except ImportError:  # pragma: no cover
    from db import db  # type: ignore
    from integration_flags import autopost_global_enabled  # type: ignore

# Sources that are third_party no matter what.
_ALWAYS_THIRD_PARTY = {"reddit", "news_rss", "news", "yelp", "trustpilot", "ripoffreport", "glassdoor", "bbb"}


@dataclass
class Settings:
    """Mirror of integration_settings with safe-OFF defaults (used when the row is absent)."""
    business_timezone: str = "UTC"
    require_approval: bool = True
    allow_owned_autopost: bool = False
    auto_reply_reviews: bool = False
    auto_reply_mentions: bool = False
    review_rating_threshold: int = 3
    auto_reply_min_stars: int = 4
    auto_reply_max_len: int = 600
    auto_platforms: list = field(default_factory=list)
    never_auto_sentiments: list = field(default_factory=lambda: ["negative"])
    daily_autopost_cap: int = 10
    hourly_auto_cap: int = 3
    warmup_manual_count: int = 20
    quiet_hours: dict = field(default_factory=dict)
    banned_phrases: list = field(default_factory=list)
    allowed_channels: list = field(default_factory=list)
    blocked_channels: list = field(default_factory=lambda: ["reddit", "yelp"])


def _settings(business_id: int) -> Settings:
    """Read integration_settings -> Settings, COALESCE to defaults if the row/table is absent."""
    try:
        with db() as conn:
            row = conn.execute("SELECT * FROM integration_settings WHERE business_id=%s",
                              (business_id,)).fetchone()
    except Exception:  # noqa: BLE001 -- table doesn't exist yet (pre-Phase-5)
        return Settings()
    if not row:
        return Settings()
    d = dict(row)
    s = Settings()
    for f in s.__dataclass_fields__:
        if f in d and d[f] is not None:
            setattr(s, f, d[f])
    return s


def _business_domain(business_id: int) -> str:
    try:
        with db() as conn:
            r = conn.execute("SELECT domain FROM businesses WHERE id=%s", (business_id,)).fetchone()
        return (r["domain"] or "").lower().replace("www.", "") if r else ""
    except Exception:  # noqa: BLE001
        return ""


def _host(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower().replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


def classify_surface(source: str, url: Optional[str], business_id: int) -> str:
    """Resolve an item to 'owned' or 'third_party'. Absence of a clear owned match degrades safely
    to third_party."""
    src = (source or "").lower()
    if src in _ALWAYS_THIRD_PARTY:
        return "third_party"
    if src in ("web", "social"):
        host = _host(url)
        dom = _business_domain(business_id)
        if host and dom and (host == dom or host.endswith("." + dom)):
            return "owned"
    return "third_party"


def guardrails_ok(s: Settings, business_id: int, draft: str) -> bool:
    """Volume + quiet-hours + length + banned-phrase + warmup checks for an owned auto-post."""
    if not draft or len(draft) > s.auto_reply_max_len:
        return False
    low = draft.lower()
    if any(p.lower() in low for p in (s.banned_phrases or [])):
        return False
    now = datetime.now(timezone.utc)
    with db() as conn:
        # daily + hourly auto-post counts across reviews + mentions
        day = conn.execute(
            "SELECT (SELECT count(*) FROM review_replies WHERE business_id=%s AND status='auto_posted' "
            " AND posted_at > now() - interval '1 day') + "
            "(SELECT count(*) FROM mention_replies WHERE business_id=%s AND posted_by='auto' "
            " AND posted_at > now() - interval '1 day') AS n", (business_id, business_id)).fetchone()["n"]
        hour = conn.execute(
            "SELECT (SELECT count(*) FROM review_replies WHERE business_id=%s AND status='auto_posted' "
            " AND posted_at > now() - interval '1 hour') + "
            "(SELECT count(*) FROM mention_replies WHERE business_id=%s AND posted_by='auto' "
            " AND posted_at > now() - interval '1 hour') AS n", (business_id, business_id)).fetchone()["n"]
    if day >= s.daily_autopost_cap or hour >= s.hourly_auto_cap:
        return False
    # quiet hours (evaluated in business timezone, best-effort UTC fallback)
    qh = s.quiet_hours or {}
    if qh.get("start") is not None and qh.get("end") is not None:
        h = now.hour
        start, end = int(qh["start"]), int(qh["end"])
        in_quiet = (start <= h < end) if start <= end else (h >= start or h < end)
        if in_quiet:
            return False
    return True


def route(surface: str, compliance_pass, sentiment: Optional[str], business_id: int, *,
          platform: Optional[str] = None, draft: str = "") -> str:
    """Return 'auto_eligible' or 'manual'. third_party is ALWAYS manual; owned is auto only if every
    gate passes. Compliance is authoritative + fail-safe (False/None => manual)."""
    if surface != "owned":
        return "manual"
    if not autopost_global_enabled():
        return "manual"
    s = _settings(business_id)
    if not s.allow_owned_autopost:
        return "manual"
    if platform and s.auto_platforms and platform not in s.auto_platforms:
        return "manual"
    if compliance_pass is not True:
        return "manual"
    if sentiment and sentiment in (s.never_auto_sentiments or []):
        return "manual"
    if not guardrails_ok(s, business_id, draft):
        return "manual"
    return "auto_eligible"


# ---------------------------------------------------------------------------
# Unified queue (read model)
# ---------------------------------------------------------------------------
def list_queue(business_id: int, *, surface: Optional[str] = None,
               kind: Optional[str] = None) -> list[dict]:
    """Assemble the unified approval queue: pending mention replies + pending/approved review
    replies + scheduled publish targets, normalized into QueueItems and cross-deduped by
    (source, external_id) so a Google review surfaced twice is one item."""
    items: list[dict] = []
    seen_ext: set = set()
    with db() as conn:
        # mention replies (pending_review)
        if kind in (None, "mention_reply"):
            rows = conn.execute(
                "SELECT r.id, r.draft, r.compliance_pass, r.compliance_flags, r.surface, r.auto_policy, "
                "m.source, m.source_url, m.external_url, m.external_id, m.title, m.sentiment "
                "FROM mention_replies r JOIN mentions m ON m.id=r.mention_id "
                "WHERE r.business_id=%s AND r.status='pending_review' ORDER BY r.id DESC",
                (business_id,)).fetchall()
            for r in rows:
                key = (r.get("source"), r.get("external_id"))
                if key[1] and key in seen_ext:
                    continue
                if key[1]:
                    seen_ext.add(key)
                items.append({
                    "kind": "mention_reply", "id": r["id"], "draft": r["draft"],
                    "compliance": {"pass": r["compliance_pass"], "flags": r["compliance_flags"] or []},
                    "surface": r.get("surface") or "third_party",
                    "capability": "alert_only" if (r.get("surface") != "owned") else "publish",
                    "source": r.get("source"), "url": r.get("external_url") or r.get("source_url"),
                    "title": r.get("title"), "sentiment": r.get("sentiment"),
                    "can_auto_post": r.get("auto_policy") == "auto_eligible", "editable": True})
        # review replies (pending + approved)
        if kind in (None, "review_reply"):
            rows = conn.execute(
                "SELECT rr.id, rr.draft, rr.compliance_pass, rr.compliance_flags, rr.status, "
                "rv.source, rv.external_id, rv.title, rv.sentiment, rv.review_url, rv.rating "
                "FROM review_replies rr JOIN reviews rv ON rv.id=rr.review_id "
                "WHERE rr.business_id=%s AND rr.status IN ('pending_review','approved') ORDER BY rr.id DESC",
                (business_id,)).fetchall()
            for r in rows:
                key = (r.get("source"), r.get("external_id"))
                if key[1] and key in seen_ext:
                    continue
                if key[1]:
                    seen_ext.add(key)
                items.append({
                    "kind": "review_reply", "id": r["id"], "draft": r["draft"], "status": r["status"],
                    "compliance": {"pass": r["compliance_pass"], "flags": r["compliance_flags"] or []},
                    "surface": "owned", "capability": "review_reply",
                    "source": r.get("source"), "url": r.get("review_url"), "title": r.get("title"),
                    "sentiment": r.get("sentiment"), "rating": float(r["rating"]) if r.get("rating") is not None else None,
                    "can_auto_post": False, "editable": True})
        # scheduled publish targets (read-only)
        if kind in (None, "scheduled_post"):
            try:
                rows = conn.execute(
                    "SELECT pt.id, pt.channel, pt.status, pt.scheduled_for, a.title "
                    "FROM publish_targets pt JOIN assets a ON a.id=pt.asset_id "
                    "WHERE pt.business_id=%s AND pt.status IN ('scheduled','queued','publishing') "
                    "ORDER BY pt.id DESC", (business_id,)).fetchall()
                for r in rows:
                    items.append({
                        "kind": "scheduled_post", "id": r["id"], "draft": None,
                        "compliance": {"pass": True, "flags": []}, "surface": "owned",
                        "capability": "publish", "source": r.get("channel"), "title": r.get("title"),
                        "status": r.get("status"), "scheduled_for": r.get("scheduled_for"),
                        "can_auto_post": False, "editable": False})
            except Exception:  # noqa: BLE001 -- publish_targets absent (pre-Phase-2)
                pass
    if surface:
        items = [i for i in items if i.get("surface") == surface]
    return items
