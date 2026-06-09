"""Config + structured-logging unit tests (no DB, no network)."""

from __future__ import annotations

import logging

import pytest


# ----------------------------- config -----------------------------
def test_config_valid_minimal():
    from rep_engine import config
    s = config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db"})
    assert s.orchestrator == "anthropic"
    assert 0.0 <= s.content_quality_threshold <= 1.0


def test_config_rejects_placeholder_dsn():
    from rep_engine import config
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        config.load_settings({"REP_DB_DSN": "postgresql://USER:PASSWORD@localhost/db"})


def test_config_rejects_non_postgres_dsn():
    from rep_engine import config
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        config.load_settings({"REP_DB_DSN": "mysql://x@localhost/db"})


def test_config_rejects_out_of_range_threshold():
    from rep_engine import config
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db",
                              "CONTENT_QUALITY_THRESHOLD": "5"})


def test_config_invalid_orchestrator():
    from rep_engine import config
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db",
                              "ORCHESTRATOR": "bard"})


def test_configured_engines_and_orchestrator_key():
    from rep_engine import config
    s = config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db",
                              "ANTHROPIC_API_KEY": "sk-ant-real",
                              "ORCHESTRATOR": "anthropic"})
    assert "anthropic" in s.configured_engines()
    assert s.orchestrator_key_set() is True
    # openai still placeholder -> not listed
    assert "openai" not in s.configured_engines()


def test_validate_or_explain_no_keys():
    from rep_engine import config
    ok, msgs = config.validate_or_explain({"REP_DB_DSN": "postgresql://me@localhost/db"})
    assert ok is False
    assert any("no answer-engine" in m for m in msgs)


def test_validate_or_explain_ready():
    from rep_engine import config
    ok, msgs = config.validate_or_explain({
        "REP_DB_DSN": "postgresql://me@localhost/db",
        "ANTHROPIC_API_KEY": "sk-ant-real", "ORCHESTRATOR": "anthropic"})
    assert ok is True
    assert any("configured engines" in m for m in msgs)


def test_bool_coercion():
    from rep_engine import config
    s0 = config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db",
                               "CRAWL_RESPECT_ROBOTS": "0"})
    assert s0.crawl_respect_robots is False
    s1 = config.load_settings({"REP_DB_DSN": "postgresql://me@localhost/db",
                               "CRAWL_RESPECT_ROBOTS": "true"})
    assert s1.crawl_respect_robots is True


# ----------------------------- logging -----------------------------
def test_log_context_binding(capsys):
    from rep_engine import logging_setup as ls
    ls.clear()
    log = ls.get_logger("test.ctx")
    ls.bind(business_id=42, run_id=7)
    log.info("hello")
    err = capsys.readouterr().err
    assert "business_id=42" in err and "run_id=7" in err and "hello" in err
    ls.clear()


def test_log_clear_removes_context(capsys):
    from rep_engine import logging_setup as ls
    log = ls.get_logger("test.clear")
    ls.bind(business_id=99)
    ls.clear()
    log.info("after clear")
    err = capsys.readouterr().err
    assert "business_id=99" not in err and "after clear" in err
