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


# --- token / slug / gap-key helpers shared by the gap <-> plan matchers -------------------
# These were re-implemented inline in ai_state_audit (the audit matcher) and content_batch
# (the batch matcher + gap keys). They had already drifted -- the two stopword vocabularies
# below differ -- so centralize the *shape* (one tokenizer, one slug, one gap key) while each
# caller keeps its own vocabulary, so the shapes can't diverge again.

_WORD4_RE = re.compile(r"[a-z]{4,}")

# Stopwords the AUDIT gap<->plan matcher drops (superset). content_batch uses a smaller set of its
# own; the two are kept distinct on purpose -- unifying them would change matching behavior.
GAP_STOPWORDS = frozenset({
    "and", "with", "the", "for", "your", "our", "page", "overview", "detail",
    "case", "studies", "story", "stories", "about", "what", "where", "which",
    "business", "company",
})


def word_set(s, *, stop=frozenset(), min_len: int = 4) -> set:
    """Lowercase alpha tokens (>= min_len chars) of `s`, minus `stop`, as a set.

    The one tokenizer shape (`[a-z]{min_len,}`) the gap/plan token-overlap matchers share.
    Callers pass their own `stop` vocabulary, so changing the shape can't silently rewrite any
    one matcher's word list.
    """
    rx = _WORD4_RE if min_len == 4 else re.compile(r"[a-z]{%d,}" % max(1, min_len))
    return {w for w in rx.findall((s or "").lower()) if w not in stop}


def gap_tokens(s) -> set:
    """`word_set` with the canonical GAP_STOPWORDS -- the audit gap-topic matcher's token set."""
    return word_set(s, stop=GAP_STOPWORDS)


def slugify(text, *, max_len: int = 60, fallback: str = "page") -> str:
    """URL-ish slug: lowercase, non-alphanumeric runs -> '-', edge-trimmed, capped, never empty."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:max_len] or fallback


def gid(source: str, topic: str) -> str:
    """Stable gap key '<source>:<lowered topic>' (e.g. 'moc:best etf funds for retirement').

    The identifier content_batch uses to name/dedupe a gap's batch across runs. Lowercased but
    NOT slugified, to match the keys already stored in content_batches.gap_key.
    """
    return f"{source}:{(topic or '').lower()}"
