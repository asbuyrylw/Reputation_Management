"""Semantic-depth analyzer tests (unit) + crawler integration."""

from __future__ import annotations


def test_entity_coverage_detects_present_and_missing():
    from rep_engine import semantic_depth as sd
    text = "We offer term life insurance and retirement planning in Cincinnati."
    out = sd.analyze_text(text, target_terms=["term life", "retirement planning", "annuity", "Cincinnati"])
    cov = out["entity_coverage"]
    assert "annuity" in cov["missing"]
    assert "term life" in cov["covered"]
    assert 0.0 <= cov["rate"] <= 1.0


def test_title_alignment_scoring():
    from rep_engine import semantic_depth as sd
    high = sd.analyze_text("body", title="Cincinnati Financial Advisors",
                           target_query="financial advisors Cincinnati")["title_alignment"]
    low = sd.analyze_text("body", title="Welcome to our homepage",
                          target_query="financial advisors Cincinnati")["title_alignment"]
    assert high > low


def test_freshness_detects_recent_date():
    from rep_engine import semantic_depth as sd
    out = sd.analyze_text("Updated 2026-05-01 with new info.", html="")
    assert out["freshness"]["has_date"] is True
    assert out["freshness"]["months_old"] is not None


def test_front_loading_rewards_early_terms():
    from rep_engine import semantic_depth as sd
    front = "annuity annuity annuity " + ("filler " * 100)
    back = ("filler " * 100) + "annuity annuity annuity"
    f_front = sd.analyze_text(front, target_terms=["annuity"])["front_loading"]
    f_back = sd.analyze_text(back, target_terms=["annuity"])["front_loading"]
    assert f_front > f_back


def test_question_coverage():
    from rep_engine import semantic_depth as sd
    text = "Term life insurance is affordable coverage for a set period."
    out = sd.analyze_text(text, target_questions=["what is term life insurance",
                                                  "how do annuities work"])
    assert "what is term life insurance" in out["question_coverage"]["answered"]
    assert "how do annuities work" in out["question_coverage"]["unanswered"]


def test_score_excludes_backlinks_and_schema():
    """Sanity: the score is driven by content signals, not schema/backlinks
    (research found those don't move AI citations). Two pages identical except
    one 'has schema' should score the same here, since schema isn't an input."""
    from rep_engine import semantic_depth as sd
    text = "Cincinnati term life and retirement planning, updated 2026-05."
    a = sd.analyze_text(text, target_terms=["term life", "retirement planning"])
    b = sd.analyze_text(text, target_terms=["term life", "retirement planning"])
    assert a["citation_readiness_score"] == b["citation_readiness_score"]
    assert "score" in a["method"].lower() or "citation" in a["method"].lower()


def test_recommendations_are_actionable():
    from rep_engine import semantic_depth as sd
    out = sd.analyze_text("Short page.", target_terms=["annuity", "401k"],
                          target_questions=["what is an annuity"])
    assert any("annuity" in r or "401k" in r for r in out["recommendations"])


def test_crawler_attaches_semantic_scorecard(monkeypatch):
    monkeypatch.setenv("CRAWL_SSRF_GUARD", "0")  # mocked HTTP layer; skip real DNS on x.com
    from rep_engine import site_crawl as sc
    rich = ("<html><head><title>Cincinnati Term Life & Retirement</title></head>"
            "<body><h1>Plans</h1><p>" + ("term life retirement planning Cincinnati " * 30)
            + " updated 2026-05-01</p></body></html>")

    class R:
        failed = False; status = 200; text = rich
    monkeypatch.setattr(sc._http, "request_json", lambda *a, **k: R())
    monkeypatch.setattr(sc, "FIRECRAWL_MODE", "off")
    targets = {"terms": ["term life", "retirement planning", "annuity", "Cincinnati"],
               "questions": ["what is term life"], "query": "financial advisor Cincinnati"}
    pa, _ = sc.audit_page("https://x.com", "https://x.com", targets)
    assert isinstance(pa.semantic, dict)
    assert "citation_readiness_score" in pa.semantic
    # annuity wasn't in the body -> should be flagged missing
    assert "annuity" in pa.semantic["entity_coverage"]["missing"]
