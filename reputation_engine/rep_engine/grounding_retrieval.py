"""
Grounded-facts retrieval (Phase G.1).
=====================================
Relevance-floored full-text retrieval over the client's VERIFIED source_documents, so the engine can
answer the one question generation never asks: "do we actually hold facts for THIS topic?" -- BEFORE
spending. `has_grounding(business_id, topic)` is the boolean the pre-spend coverage gate (Phase 1)
reads to BLOCK ungrounded generation; `retrieve(...)` returns the top matching facts to feed the
writer.

Lexical FTS with OR-semantics + a rank FLOOR: find the source docs that share SOME real terms with
the topic (a pricing page pulls "the pricing block" specifically, not the newest 3500 chars), and
drop weak matches below the floor so "grounded" means "generation will find real facts", not "a
stopword coincided". pgvector/embeddings are a deferred refinement -- lexical is sufficient for a
few-hundred-fact corpus and keeps the path dependency-free.

Dormant-safe / fail-loud: no docs or a not-yet-migrated table -> empty (has_grounding False), quietly.
A REAL read error is logged at ERROR and returns empty (never masquerades as "we hold facts").
"""

from __future__ import annotations

import logging
import os
import re

try:
    from .db import db
except ImportError:  # pragma: no cover
    from db import db  # type: ignore

log = logging.getLogger("grounding.retrieval")

# ts_rank_cd floor below which a match is too weak to count as grounding (matches the reference).
MIN_GROUNDING_RANK = float(os.getenv("GROUNDING_MIN_RANK", "0.02"))

_DORMANT_SQLSTATES = ("42P01", "42703", "42704")  # undefined_table / undefined_column / undefined_object
_TOK = re.compile(r"[a-z0-9]{3,}")
_STOP = {
    "the", "and", "for", "are", "was", "were", "with", "that", "this", "from", "have", "has", "had",
    "you", "your", "our", "their", "his", "her", "its", "about", "into", "over", "under", "than",
    "then", "them", "they", "what", "when", "where", "which", "who", "why", "how", "all", "any",
    "can", "will", "would", "should", "could", "does", "did", "not", "but", "out", "get", "got",
    "how", "why", "who", "page", "post", "asset", "hub", "content", "best", "top", "vs", "near",
}


def _tsquery(topic: str) -> str:
    """OR-semantics tsquery from a topic's real terms (deduped, stopwords dropped). '' when none."""
    seen: list[str] = []
    for t in _TOK.findall((topic or "").lower()):
        if t not in _STOP and t not in seen:
            seen.append(t)
    return " | ".join(seen[:20])


def _is_dormant(exc: Exception) -> bool:
    code = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    return code in _DORMANT_SQLSTATES


def retrieve(business_id: int, topic: str, *, limit: int = 6, floor: float | None = None) -> list[dict]:
    """Top ACTIVE source docs whose text matches the topic with ts_rank_cd >= floor, best first.
    Returns [{id, title, kind, snippet, rank}]. Empty when nothing matches / the corpus is dormant."""
    q = _tsquery(topic)
    if not q:
        return []
    floor = MIN_GROUNDING_RANK if floor is None else floor
    tsv = "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))"
    try:
        with db() as conn:
            rows = conn.execute(
                f"SELECT id, title, kind, left(content, 1200) AS snippet, "
                f"ts_rank_cd({tsv}, to_tsquery('english', %s)) AS rank "
                f"FROM source_documents WHERE business_id=%s AND active "
                f"AND {tsv} @@ to_tsquery('english', %s) "
                f"ORDER BY rank DESC LIMIT %s",
                (q, business_id, q, limit)).fetchall()
    except Exception as e:  # noqa: BLE001
        if _is_dormant(e):
            return []   # table/column/index not migrated yet -- legitimately no grounding
        # A real (non-dormant) read failure must NOT return [] -- that is indistinguishable from a
        # legitimate no-match and made coverage() report a FALSE 'ungrounded' (telling the owner to add
        # source material they may already have) and the generator ship ungrounded. RE-RAISE so the
        # advisory degrades to 'unknown' (coverage() catches it) and generation fails loud + retries.
        log.error("grounding.retrieve FAILED for business %s (NOT empty -- a broken read): %s",
                  business_id, e, exc_info=True)
        raise
    return [dict(r) for r in rows if float(r.get("rank") or 0.0) >= floor]


def has_grounding(business_id: int, topic: str, *, floor: float | None = None) -> bool:
    """True when the client's verified facts actually cover this topic (>= floor). The signal the
    pre-spend coverage gate reads to block ungrounded generation. Uses the SAME retrieval path the
    writer will use, so 'grounded' on the plan screen == 'generation will find facts'. A transient read
    error degrades to False (conservative: 'not grounded') rather than crashing the caller."""
    try:
        return bool(retrieve(business_id, topic, limit=1, floor=floor))
    except Exception:  # noqa: BLE001 -- a broken read -> conservatively 'not grounded', never a crash
        return False


def facts_block(business_id: int, topic: str, *, max_docs: int = 4, max_chars: int = 2400) -> str:
    """A compact, topic-RELEVANT grounding block (retrieved, not the whole corpus) for a generator
    prompt. Empty string when nothing is grounded (caller stays dormant)."""
    docs = retrieve(business_id, topic, limit=max_docs)
    if not docs:
        return ""
    parts, used = [], 0
    for d in docs:
        block = f"## {d.get('title') or 'Fact'}\n{(d.get('snippet') or '').strip()}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts).strip()
