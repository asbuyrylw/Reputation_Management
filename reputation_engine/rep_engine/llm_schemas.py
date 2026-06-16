"""
Pydantic v2 schemas for validating orchestrator LLM JSON outputs.
=================================================================
The orchestrator returns model-authored JSON parsed leniently by
``ai_state_audit._parse_json_lenient``. Lenient parsing guarantees we get *a*
dict, but not that its fields are well-typed or in range. These models turn a
garbled/garbage response into an explicit FAILURE the callers can route
(unscored row / human review) instead of silently coercing bogus values into
metrics and gates.

Design notes
------------
- ``extra='ignore'``: the real (and mocked) responses legitimately carry more
  keys than we consume (e.g. eval returns accuracy/answers_query/structure/
  tone/issues; scoring may return key_sources/missing). We validate the fields
  we depend on and ignore the rest -- so adding a field to a prompt never breaks
  validation.
- We rely on pydantic v2's default *lax* coercion, which is deliberately
  forgiving of harmless LLM variation (e.g. pass: "true" -> True) but still
  rejects genuine garbage (pass: "garbage", goal_alignment: 5, fixes: [1, 2]).
- These models validate over the ALREADY-parsed dict; they do not parse JSON and
  do not call any provider. No SDK is introduced.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScoreResult(BaseModel):
    """Per-answer reputation score (see ai_state_audit.SCORING_SYSTEM).

    Required: sentiment (one of four), goal_alignment in [-1, 1].
    mentions_contested/surfaces_owned default to False when the model omits them
    (a missing boolean signal is treated as 'not observed', matching the DB
    column defaults). key_sources/missing are optional context arrays.
    """

    model_config = ConfigDict(extra="ignore")

    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    goal_alignment: float = Field(ge=-1.0, le=1.0)
    mentions_contested: bool = False
    surfaces_owned: bool = False
    # awareness: does the AI actually RECOGNIZE this specific business (True) vs give a
    # generic/no-information answer (False)? Separates an awareness gap (a void to fill --
    # faster) from a negative narrative (entrenched negatives to crowd out -- slower).
    awareness: bool = True
    # entity_confusion: the answer confidently describes a DIFFERENT entity that merely shares
    # the name (wrong company/person/product), not THIS business. When True, the answer's
    # sentiment/contested mentions are about the wrong entity and must NOT be read as this
    # business's reputation -- it is a disambiguation/grounding failure, tracked separately
    # from both an awareness gap and a negative narrative.
    entity_confusion: bool = False
    key_sources: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class EvalResult(BaseModel):
    """Content self-evaluation (see content_generator.EVAL_SYSTEM).

    Required: score in [0, 1]. fixes is the actionable revision list (defaults to
    empty). Extra rubric keys (accuracy/answers_query/structure/tone/issues) are
    ignored -- we only act on score + fixes.
    """

    model_config = ConfigDict(extra="ignore")

    score: float = Field(ge=0.0, le=1.0)
    fixes: list[str] = Field(default_factory=list)


class ComplianceResult(BaseModel):
    """Compliance screen (see content_generator.COMPLIANCE_SYSTEM).

    'pass' is Optional[bool]: True (clean), False (flagged), or None (the
    screener could not decide). flags is the list of concern strings. We use a
    'pass' alias because 'pass' is a Python keyword; ``populate_by_name`` lets
    internal code also construct with pass_ if ever needed, and callers/DB get
    the literal 'pass' key back via ``model_dump(by_alias=True)``.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    pass_: Optional[bool] = Field(default=None, alias="pass")
    flags: list[str] = Field(default_factory=list)
