"""answer_flags.is_wrong_entity -- the single NULL-safe entity-exclusion rule (Phase 0.4).

Locks that a NULL / missing entity_confusion is treated as NOT-confused (the answer still counts),
and that this reproduces BOTH legacy inline coercions (narrative_score's `.get`, challenge's `_ec`)
so the narrative score and the challenge profile can never disagree on which answers to exclude.
"""
from __future__ import annotations

from rep_engine.answer_flags import is_wrong_entity


class _Row:
    """A psycopg-style row: supports []/keys() but NOT .get -- proves the defensive path."""
    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        return self._d[k]

    def keys(self):
        return self._d.keys()


def test_true_only_when_flag_true():
    assert is_wrong_entity({"entity_confusion": True}) is True
    assert is_wrong_entity({"entity_confusion": False}) is False


def test_null_and_missing_are_not_confused():
    assert is_wrong_entity({"entity_confusion": None}) is False   # NULL (unknown/failed/legacy)
    assert is_wrong_entity({}) is False                           # column absent from the SELECT


def test_works_on_mapping_row_without_get():
    assert is_wrong_entity(_Row({"entity_confusion": True})) is True
    assert is_wrong_entity(_Row({"entity_confusion": None})) is False
    assert is_wrong_entity(_Row({})) is False                     # missing key -> False, no raise


def test_reproduces_narrative_score_legacy_filter():
    # narrative_score excluded rows via `not a.get("entity_confusion")`; parity must hold for all values
    for v in (True, False, None):
        a = {"entity_confusion": v}
        assert (not a.get("entity_confusion")) == (not is_wrong_entity(a))


def test_reproduces_challenge_legacy_ec():
    # challenge._ec: bool(r["entity_confusion"]) if present else False
    def legacy_ec(r):
        return bool(r["entity_confusion"]) if "entity_confusion" in r.keys() else False
    for d in ({"entity_confusion": True}, {"entity_confusion": False},
              {"entity_confusion": None}, {}):
        assert legacy_ec(_Row(d)) == is_wrong_entity(_Row(d))
