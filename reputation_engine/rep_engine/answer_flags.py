"""
Shared, NULL-safe coercions for per-answer scoring flags (Phase 0.4 foundation).
================================================================================
`answers.entity_confusion` is a nullable BOOLEAN: TRUE only when an engine's answer confidently
describes a DIFFERENT business that merely SHARES the client's name; NULL for legacy (pre-alembic
0017), failed, or awareness-less rows. Every scorer must treat that NULL the same way -- as "not a
wrong-entity answer" -- or the same run yields different numbers depending on which module read it.

That coercion was reimplemented inline in narrative_score (`not a.get("entity_confusion")`) and
challenge (`_ec`, guarding a possibly-absent column), and coerced again at each write site. This is
the single definition, so the exclusion rule can't drift between the narrative score, the challenge
profile, and the (future) pre-spend coverage gate.

Pure, no I/O. Accepts anything mapping-like: a plain dict, a psycopg dict-row, or an LLM score dict.
"""

from __future__ import annotations


def is_wrong_entity(row) -> bool:
    """True IFF this answer is flagged as describing a DIFFERENT same-named entity
    (`entity_confusion` is TRUE). A NULL or a missing column -- unknown, failed, or a legacy
    pre-0017 row -- is treated as NOT confused (False), so the answer still counts toward the
    business's score. The one place that rule lives.

    A wrong-entity answer must be EXCLUDED from THIS business's narrative/negativity scoring: it
    isn't about them, so counting it would dilute the denominator and drag the headline toward 50.
    """
    get = getattr(row, "get", None)
    if callable(get):
        val = get("entity_confusion")
    else:  # a mapping without .get (e.g. a bare sequence row) -- read defensively
        try:
            val = row["entity_confusion"]
        except (KeyError, IndexError, TypeError):
            val = None
    return bool(val) if val is not None else False
