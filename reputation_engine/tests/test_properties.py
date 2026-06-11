"""Property-based tests (hypothesis) for the pure helpers.

These fuzz invariants that example-based unit tests can miss -- e.g. that
strip_www never removes anything but a single leading 'www.', that split_terms
tokens are always clean, and that the usage normalizer accepts every provider
shape for arbitrary token counts.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from rep_engine import textutils as tu


@given(st.text())
def test_strip_www_removes_only_a_leading_prefix(s):
    out = tu.strip_www(s)
    assert s.endswith(out)                                   # result is a suffix of input
    assert len(out) == (len(s) - 4 if s.startswith("www.") else len(s))
    if not s.startswith("www."):
        assert out == s                                      # never touches a non-www string


@given(st.text())
def test_split_terms_tokens_are_clean(s):
    for t in tu.split_terms(s):
        assert t                                             # never a blank token
        assert t == t.strip()                                # never surrounding whitespace
        assert "," not in t                                  # comma is always a separator


@given(st.text())
def test_split_terms_extra_seps_never_yields_a_semicolon(s):
    # with ';' as an extra separator, no token may still contain one
    assert all(";" not in t for t in tu.split_terms(s, extra_seps=";"))


@given(st.integers(min_value=0, max_value=10**7), st.integers(min_value=0, max_value=10**7))
def test_usage_normalizes_every_provider_shape(i, o):
    from rep_engine import ai_state_audit as m
    assert m._usage({"usage": {"input_tokens": i, "output_tokens": o}}) == {"input": i, "output": o}
    assert m._usage({"usage": {"prompt_tokens": i, "completion_tokens": o}}) == {"input": i, "output": o}
    assert m._usage({"usageMetadata": {"promptTokenCount": i,
                                       "candidatesTokenCount": o}}) == {"input": i, "output": o}
