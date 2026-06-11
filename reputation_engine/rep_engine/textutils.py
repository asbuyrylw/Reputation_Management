"""
Shared pure text helpers (no I/O, no third-party deps).

These small functions were re-implemented -- and allowed to drift -- across
several modules. Centralizing them gives one canonical behavior and a single
place to test it. Callers keep their historical private names via thin
re-export aliases, so this is a pure refactor with no behavior change.
"""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s)\]]+")


def strip_www(d: str) -> str:
    """Strip a leading 'www.' prefix only.

    Deliberately NOT str.lstrip('www.'), which strips any leading run of the
    characters {w, ., } and would corrupt e.g. 'www.weather.com' -> 'eather.com'.
    """
    return d[4:] if d.startswith("www.") else d


def extract_urls(text: str) -> list[str]:
    """Every http(s) URL in `text` (greedy up to whitespace, ')' or ']')."""
    return _URL_RE.findall(text or "")


def split_terms(csv_val, *, extra_seps: str = "") -> list[str]:
    """Split a delimited string into stripped, non-empty tokens.

    Comma-separated by default. Pass extra_seps to treat additional characters
    as separators too -- e.g. split_terms(v, extra_seps=";") splits on both ';'
    and ',', matching the crawler's seed parsing, while the audit/scoring path
    stays comma-only. A literal ';' is therefore NOT a separator unless asked
    for, so a contested term that contains one is preserved as a single token.
    """
    s = csv_val or ""
    for sep in extra_seps:
        s = s.replace(sep, ",")
    return [t.strip() for t in s.split(",") if t.strip()]
