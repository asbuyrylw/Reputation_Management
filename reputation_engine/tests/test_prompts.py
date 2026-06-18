"""User-managed prompts tests -- unit (validation) + integration (CRUD, battery merge,
AI-suggest no-key path). The LLM suggest path is exercised only for its no-key behavior."""

from __future__ import annotations

import pytest
from conftest import requires_db


def _subject(conn, name="Subject Co", domain="subject.com"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, contested_terms, geo, services) "
        "VALUES (%s,%s,'win','MLM','Cincinnati, OH','financial services') RETURNING id",
        (name, domain),
    ).fetchone()
    conn.commit()
    return r["id"]


# ----------------------------- unit -----------------------------
@requires_db
def test_add_validation(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    with pytest.raises(ValueError):
        p.add_prompt(bid, "   ")                       # empty
    with pytest.raises(ValueError):
        p.add_prompt(bid, "x" * (p.MAX_PROMPT_LEN + 1))  # too long


# ----------------------------- integration -----------------------------
@requires_db
def test_crud_and_dedupe(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    pid = p.add_prompt(bid, "Is Subject Co legit?", topic="Legitimacy", tags="a,b")
    assert pid
    # idempotent upsert on text -> same id, fields updated
    pid2 = p.add_prompt(bid, "Is Subject Co legit?", topic="Trust")
    assert pid2 == pid
    rows = p.list_prompts(bid)
    assert len(rows) == 1 and rows[0]["topic"] == "Trust"
    # update + delete
    assert p.update_prompt(bid, pid, enabled=False) is True
    assert p.list_prompts(bid)[0]["enabled"] is False
    assert p.delete_prompt(bid, pid) is True
    assert p.list_prompts(bid) == []
    # tenancy: can't update/delete another business's row
    other = _subject(conn, name="Other Co", domain="other.com")
    pid3 = p.add_prompt(other, "Other prompt")
    assert p.update_prompt(bid, pid3, enabled=False) is False
    assert p.delete_prompt(bid, pid3) is False


@requires_db
def test_only_enabled_merge_into_battery(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    from rep_engine import ai_state_audit as m
    bid = _subject(conn)
    p.add_prompt(bid, "Custom ENABLED question about Subject Co", enabled=True)
    p.add_prompt(bid, "Custom DISABLED suggestion", source="ai_suggested", enabled=False)

    assert set(p.custom_prompt_texts(bid)) == {"Custom ENABLED question about Subject Co"}

    b = dict(conn.execute("SELECT * FROM businesses WHERE id=%s", (bid,)).fetchone())
    battery = m.build_prompt_battery(b)
    assert "Custom ENABLED question about Subject Co" in battery
    assert "Custom DISABLED suggestion" not in battery
    assert len(battery) == len(set(battery))    # deduped


@requires_db
def test_cap_blocks_new_inserts(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    monkeypatch.setattr(p, "MAX_PROMPTS", 3)
    for i in range(3):
        assert p.add_prompt(bid, f"prompt {i}")
    assert p.add_prompt(bid, "one too many") is None     # capped
    # but updating an existing one still works at the cap
    assert p.add_prompt(bid, "prompt 0", topic="updated") is not None


@requires_db
def test_suggest_no_key_is_noop(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import prompts as p
    from rep_engine import ai_state_audit as m
    bid = _subject(conn)
    # force the orchestrator to return nothing (offline) -> no rows added, no crash
    monkeypatch.setattr(m, "orchestrator_json", lambda *a, **k: {})
    out = p.suggest(bid, quiet=True)
    assert out["suggested"] == 0
    assert p.list_prompts(bid) == []


@requires_db
def test_suggest_saves_disabled_for_review(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import prompts as p
    from rep_engine import ai_state_audit as m
    bid = _subject(conn)
    monkeypatch.setattr(m, "orchestrator_json", lambda *a, **k: {
        "prompts": [{"prompt": "Is Subject Co good for retirees?", "topic": "Fit", "tags": "persona"}]
    })
    out = p.suggest(bid, quiet=True)
    assert out["suggested"] == 1
    rows = p.list_prompts(bid)
    assert len(rows) == 1
    assert rows[0]["source"] == "ai_suggested" and rows[0]["enabled"] is False
    # a disabled suggestion does NOT enter the battery until enabled
    assert p.custom_prompt_texts(bid) == []


@requires_db
def test_add_never_flips_existing_enabled(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    pid = p.add_prompt(bid, "Shared text", enabled=True)
    # an AI suggestion colliding with an ENABLED prompt must NOT disable it
    assert p.add_prompt(bid, "Shared text", source="ai_suggested", enabled=False) == pid
    assert p.list_prompts(bid)[0]["enabled"] is True
    assert p.custom_prompt_texts(bid) == ["Shared text"]
    # a user re-add must NOT re-enable a paused prompt (but may refresh metadata)
    p.update_prompt(bid, pid, enabled=False)
    p.add_prompt(bid, "Shared text", topic="new topic")
    row = p.list_prompts(bid)[0]
    assert row["enabled"] is False and row["topic"] == "new topic"


@requires_db
def test_suggest_skips_existing(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import prompts as p
    from rep_engine import ai_state_audit as m
    bid = _subject(conn)
    p.add_prompt(bid, "Is Subject Co legit?", enabled=True)
    monkeypatch.setattr(m, "orchestrator_json", lambda *a, **k: {
        "prompts": [{"prompt": "Is Subject Co legit?"}, {"prompt": "A genuinely new one"}]
    })
    out = p.suggest(bid, quiet=True)
    assert out["suggested"] == 1                     # only the genuinely-new prompt
    rows = {r["prompt"]: r for r in p.list_prompts(bid)}
    assert rows["Is Subject Co legit?"]["enabled"] is True    # untouched, still tracked
    assert rows["A genuinely new one"]["enabled"] is False


@requires_db
def test_enabled_cap(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    monkeypatch.setattr(p, "MAX_ENABLED_PROMPTS", 2)
    p.add_prompt(bid, "e1"); p.add_prompt(bid, "e2")
    with pytest.raises(ValueError):
        p.add_prompt(bid, "e3")                       # 3rd ENABLED rejected
    pid = p.add_prompt(bid, "e3", enabled=False)      # but disabled is fine
    assert pid
    with pytest.raises(ValueError):
        p.update_prompt(bid, pid, enabled=True)       # enabling past the cap rejected


@requires_db
def test_update_no_fields_returns_false(fresh_schema):
    conn = fresh_schema
    from rep_engine import prompts as p
    bid = _subject(conn)
    pid = p.add_prompt(bid, "x")
    assert p.update_prompt(bid, pid) is False
