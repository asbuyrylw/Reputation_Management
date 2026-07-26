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


# Below this goal_alignment, a CONTESTED-term mention is treated as the contested/negative narrative
# WINNING (not merely "a contested word appeared"). The single source of truth, shared by the
# narrative score and the challenge profile: narrative_score used <=-0.15 while challenge used <0, so
# a mildly-negative contested mention (-0.15 < ga < 0) was 'negative' to one scorer and 'neutral' to
# the other -- feeding the gap model conflicting signals from the same run. -0.15 (the stricter,
# calibrated value) also guards against the known goal_alignment over-penalty counting a mild-negative
# as a full-negative. Change it here and BOTH scorers move together.
CONTESTED_GA = -0.15


# The SINGLE SQL predicate that excludes wrong-entity answers from any HEADLINE goal_alignment
# aggregation (the 0-100 AI-Reputation score + its per-run / per-engine / per-prompt rollups). A
# name-colliding tenant's "that's a different company" answers describe someone else, so counting them
# dilutes the denominator and drags the headline toward 50 -- exactly what is_wrong_entity() excludes in
# Python. Interpolate this literal into the score SQL so every surface shares ONE denominator and the
# exclusion can never drift between report_generator, run_metrics, and the audits router. Pair it with
# the usual `NOT COALESCE(failed,false)`. (Safe to f-string: a fixed literal, no user input.)
NOT_WRONG_ENTITY_SQL = "NOT COALESCE(entity_confusion,false)"


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
