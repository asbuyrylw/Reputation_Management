"""Phase 1 — verified-retrieval grounding + per-engine metrics.

Offline only (HTTP mocked; never spends): each engine sends the correct grounding tool
block and sets a per-answer `grounded` flag from the response; per_engine_metrics reports
per-engine KPIs with sample sizes, confidence intervals, grounding coverage, and a
partial-coverage flag.
"""

from __future__ import annotations

from types import SimpleNamespace

from conftest import requires_db


def _capture(cap, data):
    """A fake _llm_http: records the request and returns a successful canned response."""
    def fake(method, url, *, headers=None, json=None, **kw):
        cap["url"] = url
        cap["json"] = json
        return SimpleNamespace(failed=False, data=data, error=None)
    return fake


# ---------------------------------------------------------------------------
# request shaping + grounded flag, per engine
# ---------------------------------------------------------------------------
def test_anthropic_sends_web_search_and_marks_grounded(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "ANTHROPIC_API_KEY", "sk-ant-real")
    cap = {}
    data = {
        "content": [
            {"type": "text", "text": "Acme is "},
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "url": "https://x.com/a", "title": "A"}]},
            {"type": "text", "text": "well regarded.",
             "citations": [{"type": "web_search_result_location", "url": "https://x.com/a"}]},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5,
                  "server_tool_use": {"web_search_requests": 1}},
    }
    monkeypatch.setattr(m, "_llm_http", _capture(cap, data))
    ans = m.AnthropicEngine().answer("Is Acme legit?")
    tool = cap["json"]["tools"][0]
    assert tool["type"] == "web_search_20250305" and tool["name"] == "web_search"
    assert ans["grounded"] is True
    assert ans["text"] == "Acme is well regarded."        # text blocks concatenated
    assert "https://x.com/a" in ans["sources"]


def test_anthropic_ungrounded_when_no_search(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "ANTHROPIC_API_KEY", "sk-ant-real")
    data = {"content": [{"type": "text", "text": "From memory, Acme is fine."}],
            "usage": {"input_tokens": 3, "output_tokens": 4}}
    monkeypatch.setattr(m, "_llm_http", _capture({}, data))
    ans = m.AnthropicEngine().answer("Is Acme legit?")
    assert ans["grounded"] is False


def test_gemini_sends_google_search_and_marks_grounded(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "GEMINI_API_KEY", "real-gemini")
    cap = {}
    data = {"candidates": [{
        "content": {"parts": [{"text": "Acme is reputable."}]},
        "groundingMetadata": {"webSearchQueries": ["Acme reviews"],
                              "groundingChunks": [{"web": {"uri": "https://g/redir", "title": "s"}}]},
    }], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 4}}
    monkeypatch.setattr(m, "_llm_http", _capture(cap, data))
    ans = m.GeminiEngine().answer("Is Acme legit?")
    assert cap["json"]["tools"] == [{"google_search": {}}]   # 2.0+ shape, not retrieval
    assert ans["grounded"] is True
    assert "https://g/redir" in ans["sources"]


def test_openai_detects_web_search_call(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "OPENAI_API_KEY", "sk-openai")
    cap = {}
    data = {"output_text": "Acme is solid.",
            "output": [
                {"type": "web_search_call", "status": "completed",
                 "action": {"type": "search", "query": "Acme"}},
                {"type": "message", "content": [
                    {"annotations": [{"type": "url_citation", "url": "https://o/1"}]}]},
            ]}
    monkeypatch.setattr(m, "_llm_http", _capture(cap, data))
    ans = m.OpenAISearchEngine().answer("Is Acme legit?")
    assert cap["json"]["tools"] == [{"type": "web_search"}]
    assert ans["grounded"] is True
    assert "https://o/1" in ans["sources"]


def test_grounding_kill_switch_omits_tools(monkeypatch):
    """ENGINE_GROUNDING=0 is the ops fallback: no grounding tool is attached (so a
    provider/org without web search doesn't fail every answer), and grounded is False."""
    from rep_engine import ai_state_audit as m
    monkeypatch.setenv("ENGINE_GROUNDING", "0")
    monkeypatch.setattr(m, "ANTHROPIC_API_KEY", "sk-ant-real")
    cap = {}
    data = {"content": [{"type": "text", "text": "From memory."}],
            "usage": {"input_tokens": 1, "output_tokens": 1}}
    monkeypatch.setattr(m, "_llm_http", _capture(cap, data))
    ans = m.AnthropicEngine().answer("q")
    assert "tools" not in cap["json"]          # no web_search tool attached
    assert ans["grounded"] is False


def test_perplexity_grounded_iff_citations(monkeypatch):
    from rep_engine import ai_state_audit as m
    monkeypatch.setattr(m, "PERPLEXITY_API_KEY", "pplx-real")
    grounded = {"choices": [{"message": {"content": "info"}}], "citations": ["https://p/1"]}
    monkeypatch.setattr(m, "_llm_http", _capture({}, grounded))
    assert m.PerplexityEngine().answer("q")["grounded"] is True
    bare = {"choices": [{"message": {"content": "info"}}]}
    monkeypatch.setattr(m, "_llm_http", _capture({}, bare))
    assert m.PerplexityEngine().answer("q")["grounded"] is False


# ---------------------------------------------------------------------------
# detection helpers (pure) + stats
# ---------------------------------------------------------------------------
def test_grounding_detectors():
    from rep_engine import ai_state_audit as m
    assert m._anthropic_grounded({"usage": {"server_tool_use": {"web_search_requests": 2}},
                                  "content": []})[0] is True
    assert m._anthropic_grounded({"usage": {}, "content": [{"type": "text", "text": "x"}]})[0] is False
    g, s = m._gemini_grounded({"groundingMetadata": {"groundingChunks": [{"web": {"uri": "u"}}]}})
    assert g is True and s == ["u"]
    assert m._gemini_grounded({"content": {"parts": [{"text": "x"}]}})[0] is False
    assert m._openai_grounded({"output": [{"type": "web_search_call"}]})[0] is True
    assert m._openai_grounded({"output_text": "x"})[0] is False   # no output list -> not grounded


def test_wilson_and_mean_ci():
    from rep_engine import ai_state_audit as m
    assert m._wilson(0, 0) is None
    w = m._wilson(5, 10)
    assert 0 < w["low"] < w["p"] < w["high"] < 1 and w["n"] == 10
    assert m._mean_ci([]) is None
    one = m._mean_ci([0.5])
    assert one["mean"] == 0.5 and one["low"] is None          # n<2 -> no interval
    ci = m._mean_ci([0.4, 0.6, 0.5])
    assert ci["low"] < ci["mean"] < ci["high"]


# ---------------------------------------------------------------------------
# per_engine_metrics + partial coverage (DB)
# ---------------------------------------------------------------------------
def _seed_run_with_answers(conn, rows):
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                       "VALUES (%s, now(), 'complete') RETURNING id", (bid,)).fetchone()["id"]
    for engine, ga, grounded, contested, owned in rows:
        conn.execute(
            "INSERT INTO answers (run_id, business_id, engine, goal_alignment, "
            "mentions_contested, surfaces_owned, grounded, failed) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,false)",
            (rid, bid, engine, ga, contested, owned, grounded),
        )
    conn.commit()
    return bid, rid


@requires_db
def test_per_engine_metrics_and_partial_coverage(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid, rid = _seed_run_with_answers(conn, [
        ("perplexity", 0.6, True, False, True),
        ("perplexity", 0.7, True, False, True),
        ("perplexity", 0.8, True, True, False),
        ("anthropic", 0.2, False, True, False),
        ("anthropic", 0.3, False, False, False),
    ])
    out = m.per_engine_metrics(bid)
    assert out["run_id"] == rid
    assert set(out["engines"]) == {"perplexity", "anthropic"}
    pe = out["engines"]["perplexity"]
    assert pe["n"] == 3
    assert pe["grounded_rate"]["p"] == 1.0          # all 3 grounded
    assert pe["goal_alignment"]["low"] is not None  # CI present at n>=2
    assert out["engines"]["anthropic"]["grounded_rate"]["p"] == 0.0
    # only 2 of the 4 canonical engines ran -> partial coverage
    cov = out["coverage"]
    assert cov["partial"] is True
    assert set(cov["missing"]) == {"openai_search", "gemini"}


@requires_db
def test_per_engine_metrics_is_tenant_scoped(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid_a, rid_a = _seed_run_with_answers(conn, [("perplexity", 0.5, True, False, True)])
    other = conn.execute("INSERT INTO businesses (name, domain) VALUES ('B','b.com') RETURNING id").fetchone()["id"]
    conn.commit()
    # business B asking for A's run id must get nothing (no cross-tenant leak)
    out = m.per_engine_metrics(other, rid_a)
    assert out["engines"] == {}
