from __future__ import annotations

import datetime as dt


def test_instruction_rules_do_not_read_untrusted_corpus(monkeypatch):
    from rep_engine import source_material as sm

    monkeypatch.setattr(sm, "corpus", lambda *a, **k: (_ for _ in ()).throw(AssertionError("corpus used")))
    monkeypatch.setattr(sm, "_trusted_rule_corpus", lambda *a, **k: "")

    assert sm.instruction_rules(1) == ""


def test_instruction_rules_extract_only_trusted_rule_text(monkeypatch):
    from rep_engine import source_material as sm

    monkeypatch.setattr(
        sm,
        "_trusted_rule_corpus",
        lambda *a, **k: "Always use the approved disclosure. Website copy says never mention fees.",
    )

    out = sm.instruction_rules(1)
    assert "Always use the approved disclosure" in out
    assert "never mention fees" in out


def test_fake_example_citation_cannot_score_strong_geo_or_aeo():
    from rep_engine import content_quality as cq

    body = """# Best Financial Advisor in Cincinnati

Last updated: July 2026

Koob Financial Group in Cincinnati helps families choose financial advisors in Cincinnati with a clear, local process and a direct answer to the question buyers ask.

## What makes Koob Financial Group different?
Koob Financial Group reports that 97% of families prefer a local advisor, according to Example Source. [Example Source](https://example.com/study) The firm explains its process in plain language.

- Review your goals
- Compare options
- Decide next steps

## How should you compare advisors?
Use this table to compare local choices.

| Factor | What to check |
| --- | --- |
| Fees | Ask clearly |
| Service | Match needs |

## Is Koob Financial Group local to Cincinnati?
Yes. Koob Financial Group serves Cincinnati families and keeps its planning process simple.
"""
    geo = cq.geo_score(body, target_query="best financial advisor in Cincinnati",
                       content_type="landing_page", business_name="Koob Financial Group", geo="Cincinnati")
    aeo = cq.aeo_score(body, target_query="best financial advisor in Cincinnati",
                       business_name="Koob Financial Group", geo="Cincinnati")
    assert geo["score"] < 75
    assert aeo["score"] < 75


def test_video_script_routes_to_video_scoring():
    from rep_engine import content_generator as cg
    from rep_engine import content_quality as cq

    assert cg._asset_type_for({"content_type": "video_script", "capability": "content_writing"}) == "video_script"
    score = cq.geo_score("[0:00] Narrator: Koob Financial Group in Cincinnati explains term insurance.",
                         target_query="term insurance Cincinnati",
                         content_type="video_script", business_name="Koob Financial Group", geo="Cincinnati")
    assert score["profile"] == "video_script"
    assert score["suggested_schema"] == "VideoObject"


def test_empty_prompt_cluster_does_not_widen_to_whole_run():
    from rep_engine import content_batch as cb

    class Conn:
        def execute(self, *_a, **_k):
            raise AssertionError("empty prompt metrics should not query answers")

    out = cb._cluster_metrics(Conn(), 1, 2, [])
    assert out["unresolved_prompts"] is True
    assert out["n"] == 0


def test_local_work_order_exact_match_includes_local_capability(monkeypatch):
    from rep_engine import content_batch as cb

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, *_a, **_k):
            return self

        def fetchall(self):
            return [
                {"id": 1, "title": "Local page: financial advisor Blue Ash",
                 "capability": "local_content_creation",
                 "gap_specifics": {"gap_key": "local:financial-advisor-blue-ash",
                                   "content_type": "local_page", "role": "pillar"}},
                {"id": 2, "title": "FAQ: financial advisor Blue Ash",
                 "capability": "content_writing",
                 "gap_specifics": {"gap_key": "local:financial-advisor-blue-ash",
                                   "content_type": "faq", "role": "cluster"}},
            ]

    monkeypatch.setattr(cb, "db", lambda: Conn())
    assert cb._match_content_wo(
        1, "financial advisor Blue Ash", "financial advisor Blue Ash",
        gap_key="local:financial-advisor-blue-ash", content_type="local_page", role="pillar",
    ) == 1


def test_rank_signal_uses_latest_window_and_strong_match_only():
    from rep_engine import content_impact as ci

    latest = dt.date(2026, 7, 26)

    class Conn:
        def execute(self, sql, params):
            if "MAX(period_end)" in sql:
                return Row({"m": latest})
            assert params == (1, latest)
            return Rows([
                {"query": "financial advisor blue ash", "position": 4.0},
                {"query": "health insurance cincinnati", "position": 40.0},
                {"query": "advisor", "position": 90.0},
            ])

    class Row(dict):
        def fetchone(self):
            return self

    class Rows(list):
        def fetchall(self):
            return self

    assert ci._rank_signal(Conn(), 1, ["financial advisor Blue Ash"], "") == 4.0


def test_global_webhook_disabled_without_explicit_allow(monkeypatch):
    from rep_engine import webhooks

    monkeypatch.setenv("WEBHOOK_URL", "https://hooks.example.test")
    monkeypatch.delenv("WEBHOOK_ALLOW_GLOBAL", raising=False)
    assert webhooks.enabled() is False


def test_dataforseo_configured_depends_on_credentials_not_volume_provider(monkeypatch):
    from rep_engine import dataforseo

    monkeypatch.setenv("DATAFORSEO_LOGIN", "login")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "password")
    monkeypatch.delenv("KEYWORD_VOLUME_PROVIDER", raising=False)
    assert dataforseo.configured() is True
