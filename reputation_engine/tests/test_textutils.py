"""Unit tests for the shared pure text helpers (no DB / no LLM)."""

from __future__ import annotations

from rep_engine import textutils as tu


def test_strip_www_only_removes_one_prefix():
    assert tu.strip_www("www.weather.com") == "weather.com"
    # NOT str.lstrip('www.') -- that would mangle 'weather.com' -> 'eather.com'
    assert tu.strip_www("weather.com") == "weather.com"
    assert tu.strip_www("www.www.x") == "www.x"        # strips exactly one 'www.'
    assert tu.strip_www("") == ""


def test_split_terms_is_comma_only_by_default():
    assert tu.split_terms("a, b ,c") == ["a", "b", "c"]
    assert tu.split_terms("") == []
    assert tu.split_terms(None) == []
    # a semicolon is NOT a separator unless requested -> the token is preserved
    assert tu.split_terms("a;b") == ["a;b"]


def test_split_terms_extra_seps_adds_separators():
    assert tu.split_terms("a;b,c", extra_seps=";") == ["a", "b", "c"]
    assert tu.split_terms("x ; y", extra_seps=";") == ["x", "y"]


def test_extract_urls():
    assert tu.extract_urls("see https://a.com/x and http://b.org).") == [
        "https://a.com/x", "http://b.org"]
    assert tu.extract_urls("") == []
    assert tu.extract_urls(None) == []
