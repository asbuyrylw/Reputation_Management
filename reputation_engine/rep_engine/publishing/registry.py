"""
Publisher registry (Integrations Phase 2; social channels added in Phase 5)
==========================================================================
Maps a `channel` key -> (Publisher adapter, network). The runner looks up the adapter for a
target's channel. Reddit/Yelp are deliberately ABSENT (draft-suggestion / read-only only -- no
code path posts to them).
"""

from __future__ import annotations

from typing import Optional, Tuple

try:
    from .wordpress import WordPressPublisher
    from .ayrshare import AyrsharePublisher
    from .google_business import GoogleBusinessPublisher
    from .base import Connection
except ImportError:  # pragma: no cover
    from publishing.wordpress import WordPressPublisher  # type: ignore
    from publishing.ayrshare import AyrsharePublisher  # type: ignore
    from publishing.google_business import GoogleBusinessPublisher  # type: ignore
    from publishing.base import Connection  # type: ignore

_WP = WordPressPublisher()
_AYR = AyrsharePublisher()
_GBP = GoogleBusinessPublisher()

# channel -> (adapter, network). network '_' means single-target (no per-network fan-out).
# Reddit/Yelp are deliberately ABSENT (draft-suggestion / read-only only).
_CHANNELS: dict[str, Tuple[object, str]] = {
    "wp_blog": (_WP, "_"),
    "gbp_post": (_GBP, "_"),
    "social_fb_page": (_AYR, "facebook"),
    "social_ig": (_AYR, "instagram"),
    "social_li_org": (_AYR, "linkedin"),
    "social_x": (_AYR, "twitter"),
    "social_pinterest": (_AYR, "pinterest"),
}

# Which platform_connections.kind serves a given channel (router validation + connection match).
_CHANNEL_TO_KIND = {
    "wp_blog": "wordpress_org",
    "gbp_post": "google_business_profile",
    "social_fb_page": "ayrshare_profile",
    "social_ig": "ayrshare_profile",
    "social_li_org": "ayrshare_profile",
    "social_x": "ayrshare_profile",
    "social_pinterest": "ayrshare_profile",
}

# Social channels carry text, not an article body -> the runner builds a 'social' payload.
_SOCIAL_CHANNELS = {"gbp_post", "social_fb_page", "social_ig", "social_li_org", "social_x", "social_pinterest"}


def is_social(channel: str) -> bool:
    return channel in _SOCIAL_CHANNELS


def adapter_for(channel: str):
    entry = _CHANNELS.get(channel)
    return entry[0] if entry else None


def network_for(channel: str) -> str:
    entry = _CHANNELS.get(channel)
    return entry[1] if entry else "_"


def kind_for(channel: str) -> Optional[str]:
    return _CHANNEL_TO_KIND.get(channel)


def known_channels() -> list[str]:
    return list(_CHANNELS.keys())


def register(channel: str, adapter, network: str = "_", kind: Optional[str] = None) -> None:
    """Phase 5 hook: add a channel without editing this file's literal."""
    _CHANNELS[channel] = (adapter, network)
    if kind:
        _CHANNEL_TO_KIND[channel] = kind
