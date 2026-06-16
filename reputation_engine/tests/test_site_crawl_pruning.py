"""Gap-model pruning: WordPress/system crawl artifacts must not be treated as thin
content pages or content opportunities. Pure-function test -- no DB required."""

from __future__ import annotations

import pytest

from rep_engine.site_crawl import _is_crawl_artifact


@pytest.mark.parametrize("url", [
    "https://x.com/feed/",
    "https://x.com/comments/feed/",
    "https://x.com/xmlrpc.php",
    "https://x.com/wp-json/oembed/1.0/embed?url=y",
    "https://x.com/wp-content/cache/min/1/abc.css",
    "https://x.com/wp-admin/admin-ajax.php",
    "https://x.com/?replytocom=42",
    "https://x.com/assets/app.js",
    "https://x.com/logo.png",
])
def test_artifacts_are_filtered(url):
    assert _is_crawl_artifact(url) is True


@pytest.mark.parametrize("url", [
    "https://x.com/",
    "https://x.com/about",
    "https://x.com/careers",
    "https://x.com/team/chris-koob",
    "https://x.com/services/life-insurance",
])
def test_real_content_pages_are_kept(url):
    assert _is_crawl_artifact(url) is False
