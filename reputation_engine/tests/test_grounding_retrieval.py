"""Grounded-facts retrieval tests (Phase G.1) -- require REP_TEST_DSN (FTS over real Postgres)."""
from __future__ import annotations

from conftest import requires_db


def _biz(conn):
    r = conn.execute(
        "INSERT INTO businesses (name, domain, goal, geo) VALUES ('Acme','a.com','win','Denver CO') "
        "RETURNING id").fetchone()
    conn.commit()
    return r["id"]


def _doc(conn, bid, title, content, active=True, kind="general"):
    conn.execute(
        "INSERT INTO source_documents (business_id, title, source_type, content, tokens, active, kind) "
        "VALUES (%s,%s,'upload',%s,%s,%s,%s)",
        (bid, title, content, max(1, len(content) // 4), active, kind))
    conn.commit()


@requires_db
def test_has_grounding_true_for_covered_topic(fresh_schema):
    conn = fresh_schema
    from rep_engine import grounding_retrieval as gr
    bid = _biz(conn)
    _doc(conn, bid, "Pricing", "Our annual retainer pricing starts at 2500 dollars per month for the growth plan.")
    _doc(conn, bid, "Team bios", "Our founder has fifteen years of experience in reputation management.")
    assert gr.has_grounding(bid, "What is your pricing for the growth plan?") is True
    assert gr.has_grounding(bid, "annual retainer pricing") is True
    assert gr.has_grounding(bid, "underwater basket weaving techniques") is False  # no supporting facts


@requires_db
def test_retrieve_ranks_and_respects_floor(fresh_schema):
    conn = fresh_schema
    from rep_engine import grounding_retrieval as gr
    bid = _biz(conn)
    _doc(conn, bid, "Pricing", "Pricing: the growth plan retainer is 2500 per month; enterprise pricing is custom.")
    _doc(conn, bid, "About", "We are a Denver reputation firm helping local businesses.")
    hits = gr.retrieve(bid, "growth plan pricing retainer")
    assert hits and hits[0]["title"] == "Pricing"
    assert all(h["rank"] >= gr.MIN_GROUNDING_RANK for h in hits)
    assert gr.facts_block(bid, "growth plan pricing").startswith("## Pricing")


@requires_db
def test_inactive_docs_excluded(fresh_schema):
    conn = fresh_schema
    from rep_engine import grounding_retrieval as gr
    bid = _biz(conn)
    _doc(conn, bid, "Secret pricing", "The secret discount pricing is fifty percent off.", active=False)
    assert gr.has_grounding(bid, "secret discount pricing") is False   # inactive is not retrieved


@requires_db
def test_empty_topic_and_tenant_isolation(fresh_schema):
    conn = fresh_schema
    from rep_engine import grounding_retrieval as gr
    bid = _biz(conn)
    other = _biz(conn)
    _doc(conn, bid, "Pricing", "Growth plan pricing is 2500 per month.")
    assert gr.retrieve(bid, "") == []                                   # no real terms -> no query
    assert gr.has_grounding(other, "growth plan pricing") is False      # other tenant holds no docs
