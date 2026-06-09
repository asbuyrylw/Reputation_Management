"""Tiered model routing + adaptive sampling unit tests (no DB, no network)."""

from __future__ import annotations


def test_tier_model_selection():
    from rep_engine import ai_state_audit as m
    a_cheap, o_cheap = m._model_for("cheap")
    a_full, o_full = m._model_for("full")
    assert a_cheap != a_full      # cheap tier is a different (smaller) model
    assert o_cheap != o_full
    # full tier returns the configured headline models
    assert a_full == m.ORCH_MODEL_ANTHROPIC
    assert o_full == m.ORCH_MODEL_OPENAI


def test_score_answer_uses_cheap_tier(monkeypatch):
    """score_answer (high-volume) must route to the cheap tier."""
    from rep_engine import ai_state_audit as m
    captured = {}
    def fake_orch(system, user, tier="full"):
        captured["tier"] = tier
        return {"goal_alignment": 0.4, "sentiment": "neutral"}
    monkeypatch.setattr(m, "orchestrator_json", fake_orch)
    m.score_answer({"name": "X", "goal": "g", "contested_terms": ""}, "prompt", {"text": "ans"})
    assert captured["tier"] == "cheap"


def test_adaptive_stop_when_stable_and_clear():
    from rep_engine import ai_state_audit as m
    assert m._should_stop_sampling([0.5, 0.55]) is True
    assert m._should_stop_sampling([-0.6, -0.5]) is True   # clearly negative is also "clear"


def test_adaptive_continue_when_noisy():
    from rep_engine import ai_state_audit as m
    assert m._should_stop_sampling([0.1, 0.7]) is False     # spread too wide


def test_adaptive_continue_near_boundary():
    from rep_engine import ai_state_audit as m
    assert m._should_stop_sampling([0.05, 0.0, -0.05]) is False  # mean ~0, ambiguous


def test_adaptive_requires_min_samples():
    from rep_engine import ai_state_audit as m
    assert m._should_stop_sampling([0.9]) is False          # only one sample
    assert m._should_stop_sampling([]) is False
