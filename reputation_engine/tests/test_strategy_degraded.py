"""strategy_generator._is_degraded -- the ONE 'plan is boilerplate-only' signal (Phase 0.6).

Locks that assemble_plan (the persisted plan JSON) and strategy_view (the console's Strategy page)
agree on when a plan is degraded, because both now read this single definition. Pure logic, no DB.
"""
from __future__ import annotations

from rep_engine import strategy_generator as sg


def test_empty_or_missing_gap_is_degraded():
    assert sg._is_degraded({}) is True
    assert sg._is_degraded(None) is True                       # no gap model at all
    assert sg._is_degraded({"summary": "words but no gaps"}) is True   # summary alone isn't work


def test_any_gap_content_array_makes_it_real():
    for key in sg._GAP_CONTENT_KEYS:
        assert sg._is_degraded({key: [{"topic": "x"}]}) is False, f"{key} should count as real work"


def test_empty_arrays_are_still_degraded():
    # every gap-content key present but EMPTY -> baseline boilerplate only -> degraded
    assert sg._is_degraded({k: [] for k in sg._GAP_CONTENT_KEYS}) is True
