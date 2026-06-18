"""per_prompt_metrics: per-prompt visibility/sentiment/goal-alignment aggregation (DB)."""

from __future__ import annotations

from conftest import requires_db


def _seed(conn, rows, name="Acme"):
    """rows: (prompt, engine, awareness, sentiment, goal_alignment)."""
    bid = conn.execute(
        "INSERT INTO businesses (name, domain) VALUES (%s,'a.com') RETURNING id", (name,)
    ).fetchone()["id"]
    rid = conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at, status) "
        "VALUES (%s, now(), 'complete') RETURNING id", (bid,)
    ).fetchone()["id"]
    for prompt, engine, awareness, sentiment, ga in rows:
        conn.execute(
            "INSERT INTO answers (run_id, business_id, engine, prompt, awareness, sentiment, "
            "goal_alignment, surfaces_owned, mentions_contested, failed) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,false,false,false)",
            (rid, bid, engine, prompt, awareness, sentiment, ga),
        )
    conn.commit()
    return bid, rid


@requires_db
def test_per_prompt_metrics_aggregates_and_sorts(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid, rid = _seed(conn, [
        ("Is Acme legit?", "perplexity", True, "positive", 0.6),
        ("Is Acme legit?", "anthropic", True, "neutral", 0.2),
        ("Best widgets in town", "perplexity", False, "negative", -0.5),
        ("Best widgets in town", "anthropic", False, "neutral", -0.1),
    ])
    out = m.per_prompt_metrics(bid)
    assert out["run_id"] == rid and len(out["prompts"]) == 2
    # sorted lowest-visibility first -> the invisible category prompt leads
    first = out["prompts"][0]
    assert first["prompt"] == "Best widgets in town"
    assert first["visibility"] == 0.0 and first["n"] == 2
    assert first["sentiment"]["negative"] == 1 and first["sentiment"]["neutral"] == 1
    second = out["prompts"][1]
    assert second["visibility"] == 1.0
    assert set(second["engines"]) == {"perplexity", "anthropic"}
    assert second["engines"]["perplexity"]["visibility"] == 1.0
    assert second["engines"]["perplexity"]["sentiment"] == "positive"
    # sentiment breakdown always carries the 4 standard keys and sums to n
    assert set(first["sentiment"]) == {"positive", "neutral", "negative", "mixed"}
    assert sum(first["sentiment"].values()) == first["n"]


@requires_db
def test_per_prompt_metrics_excludes_failed_and_scopes_tenant(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid, rid = _seed(conn, [("Q1", "perplexity", True, "positive", 0.5)])
    # a failed answer for the same prompt must not count
    conn.execute(
        "INSERT INTO answers (run_id, business_id, engine, prompt, awareness, sentiment, "
        "goal_alignment, failed) VALUES (%s,%s,'anthropic','Q1',false,'negative',-0.9,true)",
        (rid, bid),
    )
    conn.commit()
    out = m.per_prompt_metrics(bid)
    assert out["prompts"][0]["n"] == 1 and out["prompts"][0]["visibility"] == 1.0
    # another business's run is not visible
    other = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Other','o.com') RETURNING id").fetchone()["id"]
    conn.commit()
    assert m.per_prompt_metrics(other) == {"run_id": None, "prompts": []}


@requires_db
def test_unknown_awareness_is_not_zero_visibility(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                       "VALUES (%s, now(), 'complete') RETURNING id", (bid,)).fetchone()["id"]
    # one prompt whose awareness is unknown (NULL) on every answer
    for eng in ("perplexity", "anthropic"):
        conn.execute("INSERT INTO answers (run_id, business_id, engine, prompt, awareness, "
                     "sentiment, goal_alignment, failed) VALUES (%s,%s,%s,'Q-null',NULL,'neutral',0.0,false)",
                     (rid, bid, eng))
    # one prompt that IS known but invisible (worst KNOWN)
    conn.execute("INSERT INTO answers (run_id, business_id, engine, prompt, awareness, sentiment, "
                 "goal_alignment, failed) VALUES (%s,%s,'perplexity','Q-known',false,'negative',-0.4,false)",
                 (rid, bid))
    conn.commit()
    out = m.per_prompt_metrics(bid)
    byq = {p["prompt"]: p for p in out["prompts"]}
    assert byq["Q-null"]["visibility"] is None            # unknown, NOT 0%
    assert byq["Q-known"]["visibility"] == 0.0
    # the unknown-awareness prompt sorts LAST (doesn't masquerade as most-invisible)
    assert out["prompts"][-1]["prompt"] == "Q-null"


@requires_db
def test_persona_lenses_with_same_text_stay_separate(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, finished_at, status) "
                       "VALUES (%s, now(), 'complete') RETURNING id", (bid,)).fetchone()["id"]
    # same text, two lenses -> must remain two rows, not one merged bucket
    conn.execute("INSERT INTO answers (run_id, business_id, engine, prompt, persona, awareness, "
                 "sentiment, goal_alignment, failed) VALUES (%s,%s,'perplexity','Is Acme legit?','',true,'positive',0.5,false)", (rid, bid))
    conn.execute("INSERT INTO answers (run_id, business_id, engine, prompt, persona, awareness, "
                 "sentiment, goal_alignment, failed) VALUES (%s,%s,'perplexity','Is Acme legit?','prospective_client',false,'negative',-0.5,false)", (rid, bid))
    conn.commit()
    out = m.per_prompt_metrics(bid)
    same = [p for p in out["prompts"] if p["prompt"] == "Is Acme legit?"]
    assert len(same) == 2
    assert {p["persona"] for p in same} == {"", "prospective_client"}


@requires_db
def test_per_prompt_metrics_empty(fresh_schema):
    conn = fresh_schema
    from rep_engine import ai_state_audit as m
    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','a.com') RETURNING id").fetchone()["id"]
    conn.commit()
    assert m.per_prompt_metrics(bid) == {"run_id": None, "prompts": []}
