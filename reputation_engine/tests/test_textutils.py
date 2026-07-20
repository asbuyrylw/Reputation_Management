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


# --- token / slug / gap-key helpers (Phase 0.3 centralization) ---------------------------

def test_word_set_shape_min_len_and_lowercasing():
    # lowercased, only [a-z] runs >= min_len (default 4), digits/short words dropped, deduped
    assert tu.word_set("Best ETF funds 2025 for ME") == {"best", "funds"}   # 'etf'/'for'/'me'/'2025' too short
    assert tu.word_set("Repeat repeat REPEAT") == {"repeat"}                  # set -> deduped
    assert tu.word_set("", ) == set()
    assert tu.word_set(None) == set()
    assert tu.word_set("abc abcd", min_len=3) == {"abc", "abcd"}             # min_len override


def test_word_set_honors_caller_stopwords():
    assert tu.word_set("your company page detail", stop=tu.GAP_STOPWORDS) == set()   # all stopped
    assert tu.word_set("your company detail", stop={"your"}) == {"company", "detail"}  # only 'your' dropped


def test_gap_tokens_uses_canonical_stopwords():
    # gap_tokens == word_set(..., stop=GAP_STOPWORDS); 'business'/'about' are gap-stopwords
    assert tu.gap_tokens("About our business growth") == {"growth"}
    assert tu.gap_tokens("retirement planning strategies") == {"retirement", "planning", "strategies"}


def test_slugify_matches_legacy_behavior():
    assert tu.slugify("Best ETF Funds! (2025)") == "best-etf-funds-2025"
    assert tu.slugify("  ---leading/trailing---  ") == "leading-trailing"
    assert tu.slugify("") == "page"                       # never empty -> fallback
    assert tu.slugify("!!!") == "page"
    assert len(tu.slugify("a" * 200)) == 60               # capped at 60


def test_gid_is_source_colon_lowered_topic():
    assert tu.gid("moc", "Best ETF Funds") == "moc:best etf funds"           # lowered, NOT slugified
    assert tu.gid("local", "Denver CO plumber") == "local:denver co plumber"
    assert tu.gid("comp", "") == "comp:"
    assert tu.gid("moc", None) == "moc:"


def test_delegating_aliases_preserve_behavior():
    # the audit module's private names now delegate to textutils -- identical results
    from rep_engine import ai_state_audit as audit
    assert audit._addressed_toks("About our business growth") == tu.gap_tokens("About our business growth")
    assert audit._ADDRESSED_STOPW is tu.GAP_STOPWORDS
    # content_generator._slugify delegates to the canonical slug
    from rep_engine import content_generator as cg
    assert cg._slugify("Best ETF Funds! (2025)") == "best-etf-funds-2025"
