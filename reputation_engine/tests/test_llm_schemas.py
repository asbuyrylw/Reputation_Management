"""No-DB unit tests for the LLM output validation schemas (llm_schemas.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rep_engine.llm_schemas import ComplianceResult, EvalResult, ScoreResult


def test_score_result_accepts_mocked_and_defaults_missing_booleans():
    # The cheap-tier scoring mock shape (test_cost_levers) -- booleans default to False.
    s = ScoreResult.model_validate({"goal_alignment": 0.4, "sentiment": "neutral"})
    assert s.mentions_contested is False and s.surfaces_owned is False
    full = ScoreResult.model_validate(
        {"sentiment": "positive", "goal_alignment": 0.7,
         "mentions_contested": False, "surfaces_owned": True})
    assert full.surfaces_owned is True


def test_score_result_rejects_garbled():
    for bad in (
        {},                                                  # nothing
        {"sentiment": "glorious", "goal_alignment": 0.3},    # bad enum
        {"sentiment": "neutral", "goal_alignment": 5},       # out of range
        {"sentiment": "neutral"},                            # missing goal_alignment
    ):
        with pytest.raises(ValidationError):
            ScoreResult.model_validate(bad)


def test_eval_result_accepts_all_mocked_shapes():
    # All three content_generator eval mock shapes validate (extra keys ignored).
    EvalResult.model_validate({"score": 0.9, "accuracy": True, "answers_query": True,
                               "structure": True, "tone": True, "issues": [], "fixes": []})
    EvalResult.model_validate({"score": 0.3, "fixes": ["add specifics"], "issues": ["too thin"]})
    e = EvalResult.model_validate({"score": 0.9, "fixes": []})
    dumped = e.model_dump()
    assert dumped["score"] == 0.9 and dumped["fixes"] == []
    for bad in ({}, {"score": 5}, {"score": "high"}):
        with pytest.raises(ValidationError):
            EvalResult.model_validate(bad)


def test_compliance_result_alias_roundtrip_and_garbage():
    c = ComplianceResult.model_validate({"pass": True, "flags": []})
    assert c.model_dump(by_alias=True) == {"pass": True, "flags": []}
    c2 = ComplianceResult.model_validate({"pass": False, "flags": ["implied returns"]})
    assert c2.model_dump(by_alias=True)["pass"] is False
    assert "implied returns" in c2.flags
    # null is a valid 'undecided' verdict; genuine garbage is rejected.
    assert ComplianceResult.model_validate({"pass": None}).pass_ is None
    with pytest.raises(ValidationError):
        ComplianceResult.model_validate({"pass": "garbage"})
