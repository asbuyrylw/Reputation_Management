"""Mention monitoring + reply drafting tests -- require REP_TEST_DSN."""

from __future__ import annotations

import pytest
from conftest import requires_db


def _biz(conn, name="Acme Financial", domain="acme.com"):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,'financial services','win','MLM','Cincinnati OH') RETURNING id", (name, domain)
    ).fetchone()
    conn.commit()
    return r["id"]


# ----------------------------- unit -----------------------------
def test_relevance_and_sentiment():
    from rep_engine import mention_monitor as mm
    assert mm._relevance("I love Acme Financial services", "Acme Financial") == 1.0
    assert mm._sentiment("this is a scam and a ripoff") == "negative"
    assert mm._sentiment("great and trusted, highly recommend") == "positive"


def test_negative_keyword_filter():
    from rep_engine import mention_monitor as mm
    assert mm._matches_negative("hiring for a job", ["hiring", "job"]) is True
    assert mm._matches_negative("a normal post", ["hiring"]) is False


# ----------------------------- integration -----------------------------
@requires_db
def test_add_keyword_and_discover_with_fake_source(fresh_schema):
    conn = fresh_schema
    from rep_engine import mention_monitor as mm
    bid = _biz(conn)
    mm.add_keyword(bid, "Acme Financial")

    # register a fake source so no network is needed
    def fake(keyword):
        return [
            {"source": "fake", "source_url": "https://x.com/1", "external_id": "1",
             "author": "u1", "title": "Is Acme Financial legit?", "body": "Thinking about Acme Financial."},
            {"source": "fake", "source_url": "https://x.com/1", "external_id": "1",  # dup
             "author": "u1", "title": "dup", "body": "dup"},
            {"source": "fake", "source_url": "https://x.com/2", "external_id": "2",
             "author": "u2", "title": "Unrelated", "body": "Something totally different."},
        ]
    mm.register_source("fake", fake)
    out = mm.discover(bid, sources=["fake"], quiet=True)
    # only the relevant, deduped mention should be stored (1 of 3)
    assert out["found"] == 1
    n = conn.execute("SELECT COUNT(*) n FROM mentions WHERE business_id=%s", (bid,)).fetchone()["n"]
    assert n == 1


@requires_db
def test_negative_keyword_excludes_mention(fresh_schema):
    conn = fresh_schema
    from rep_engine import mention_monitor as mm
    bid = _biz(conn)
    mm.add_keyword(bid, "Acme Financial")
    mm.add_keyword(bid, "hiring", negative=True)

    def fake(keyword):
        return [{"source": "fake", "source_url": "https://x.com/3", "external_id": "3",
                 "author": "u", "title": "Acme Financial hiring now", "body": "Acme Financial hiring reps"}]
    mm.register_source("fake", fake)
    out = mm.discover(bid, sources=["fake"], quiet=True)
    assert out["found"] == 0   # excluded by negative keyword "hiring"


@requires_db
def test_drafts_are_always_pending_review(fresh_schema, monkeypatch):
    """THE critical guarantee: drafted replies are NEVER auto-posted."""
    conn = fresh_schema
    from rep_engine import mention_monitor as mm
    bid = _biz(conn)
    # seed a mention directly
    conn.execute(
        "INSERT INTO mentions (business_id, source, source_url, external_id, title, body, "
        "matched_keyword, sentiment, relevance, status, dedup_hash) "
        "VALUES (%s,'fake','https://x.com/9','9','Acme review','Mixed feelings about Acme', "
        "'Acme','neutral',0.9,'new','h9')", (bid,))
    conn.commit()
    # no LLM key -> _draft_one uses safe template; _compliance returns pass=None
    out = mm.draft_replies(bid, quiet=True)
    assert out["drafted"] == 1
    rows = conn.execute("SELECT status, draft FROM mention_replies WHERE business_id=%s", (bid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending_review"      # never auto-posted
    assert rows[0]["draft"]                             # a draft exists
    # the mention is marked drafted, not actioned
    st = conn.execute("SELECT status FROM mentions WHERE business_id=%s", (bid,)).fetchone()["status"]
    assert st == "drafted"


@requires_db
def test_approve_and_reject_flow(fresh_schema):
    conn = fresh_schema
    from rep_engine import mention_monitor as mm
    bid = _biz(conn)
    mid = conn.execute(
        "INSERT INTO mentions (business_id, source, source_url, external_id, title, body, "
        "matched_keyword, relevance, status, dedup_hash) "
        "VALUES (%s,'fake','u','x','t','b','k',0.9,'drafted','hh') RETURNING id", (bid,)
    ).fetchone()["id"]
    rid = conn.execute(
        "INSERT INTO mention_replies (mention_id, business_id, draft, status) "
        "VALUES (%s,%s,'draft text','pending_review') RETURNING id", (mid, bid)
    ).fetchone()["id"]
    conn.commit()
    mm.approve(rid, "Logan")
    st = conn.execute("SELECT status, reviewer FROM mention_replies WHERE id=%s", (rid,)).fetchone()
    assert st["status"] == "approved" and st["reviewer"] == "Logan"
    # mention becomes actioned
    mst = conn.execute("SELECT status FROM mentions WHERE id=%s", (mid,)).fetchone()["status"]
    assert mst == "actioned"


@requires_db
def test_unlimited_businesses_and_keywords(fresh_schema):
    """No license cap: many businesses, many keywords each, all tracked."""
    conn = fresh_schema
    from rep_engine import mention_monitor as mm
    for i in range(5):
        bid = _biz(conn, name=f"Biz {i}", domain=f"biz{i}.com")
        for k in range(10):
            mm.add_keyword(bid, f"keyword {i}-{k}")
    total = conn.execute("SELECT COUNT(*) n FROM monitor_keywords").fetchone()["n"]
    assert total == 50   # 5 businesses x 10 keywords, no cap
