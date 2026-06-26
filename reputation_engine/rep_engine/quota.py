"""
Reputation Crowding-Out Engine -- shared platform-app quota accounting (Wave 5, item 22)
========================================================================================
Social/API quotas (Ayrshare monthly cap, X tier QPS/daily, GBP QPM) are ACCOUNT-level on the
shared app key -- not per-tenant -- so a busy day across ALL businesses can blow the provider
limit mid-campaign. This tracks GLOBAL successful posts per platform in a rolling window (from the
existing publish_attempts + review_replies audit rows) and checks them against env-configured caps.
No caps set => unlimited (current behavior). The publish runner consults `check()` before an
auto-post and defers when over.

    PLATFORM_QUOTA_AYRSHARE_DAILY=   PLATFORM_QUOTA_X_DAILY=   PLATFORM_QUOTA_GBP_DAILY=
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

# platform -> (env var for the daily cap, channels that count toward it)
_PLATFORMS = {
    "ayrshare": ("PLATFORM_QUOTA_AYRSHARE_DAILY",
                 ("social_fb_page", "social_ig", "social_li_org", "social_x", "social_pinterest")),
    "x": ("PLATFORM_QUOTA_X_DAILY", ("social_x",)),
    "gbp": ("PLATFORM_QUOTA_GBP_DAILY", ("gbp_post",)),
}


def _cap(platform: str) -> Optional[int]:
    env = _PLATFORMS.get(platform, (None, ()))[0]
    raw = os.getenv(env or "", "").strip() if env else ""
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def daily_usage(platform: str) -> int:
    """GLOBAL successful posts to this platform in the last 24h (across all businesses)."""
    channels = _PLATFORMS.get(platform, (None, ()))[1]
    if not channels:
        return 0
    placeholders = ",".join(["%s"] * len(channels))
    with db() as conn:
        n = conn.execute(
            f"SELECT COUNT(*) n FROM publish_attempts a JOIN publish_targets t ON t.id=a.target_id "
            f"WHERE a.ok AND a.created_at > now() - interval '1 day' AND t.channel IN ({placeholders})",
            tuple(channels)).fetchone()["n"]
        # GBP review replies count toward the GBP quota too
        if platform == "gbp":
            n += conn.execute(
                "SELECT COUNT(*) n FROM review_replies WHERE status IN ('posted','auto_posted') "
                "AND posted_at > now() - interval '1 day'").fetchone()["n"]
    return int(n)


def check(platform: str) -> dict:
    """{within: bool, used, cap}. within=True (unlimited) when no cap is configured."""
    cap = _cap(platform)
    if cap is None:
        return {"within": True, "used": None, "cap": None, "unlimited": True}
    used = daily_usage(platform)
    return {"within": used < cap, "used": used, "cap": cap, "unlimited": False}


def channel_within_quota(channel: str) -> bool:
    """Convenience for the runner: is the platform owning this channel within quota?"""
    for platform, (_env, channels) in _PLATFORMS.items():
        if channel in channels and not check(platform)["within"]:
            return False
    return True


def usage_report() -> dict:
    """All platform quotas + current usage (for an operator dashboard)."""
    return {p: check(p) for p in _PLATFORMS}
