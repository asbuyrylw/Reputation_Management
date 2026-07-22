"""JIT content generation (Phase 3) — regression lock for the due_within_days filter.

Proves generate(due_within_days=N) drafts ONLY the content pieces whose cadence slot is within N days
AND that aren't already drafted / done / superseded — so 'plan a year, generate just-in-time' drafts
each piece near its drip slot, not all at once. LLM + budget mocked (no network, no spend).
"""
from __future__ import annotations

import datetime as dt

import pytest

from conftest import requires_db


def _wo(conn, bid, title, *, days, status="pending", superseded=False):
    return conn.execute(
        "INSERT INTO work_orders (business_id, title, capability, execution, instruction, status, "
        "target_date, superseded) VALUES (%s,%s,'content_writing','auto','write it',%s,%s,%s) "
        "RETURNING id",
        (bid, title, status, dt.date.today() + dt.timedelta(days=days), superseded)).fetchone()["id"]


@requires_db
def test_generate_due_selects_only_near_due_undrafted(fresh_schema, monkeypatch):
    conn = fresh_schema
    from rep_engine import content_generator as cg

    bid = conn.execute("INSERT INTO businesses (name, domain) VALUES ('Acme','acme.com') "
                       "RETURNING id").fetchone()["id"]
    due = _wo(conn, bid, "Due soon — should draft", days=3)                 # within 7d, open, no draft
    far = _wo(conn, bid, "Far off — skip", days=40)                         # outside 7d
    drafted = _wo(conn, bid, "Already drafted — skip", days=3)              # near-due but has a draft
    done = _wo(conn, bid, "Done — skip", days=3, status="done")             # near-due but completed
    gone = _wo(conn, bid, "Superseded — skip", days=3, superseded=True)     # near-due but archived
    conn.execute("INSERT INTO content_drafts (business_id, work_order_id, title, status) "
                 "VALUES (%s,%s,'d','pending_review')", (bid, drafted))
    conn.commit()

    called: list[int] = []
    monkeypatch.setattr(cg.llm.cost, "over_budget", lambda _bid: False)
    monkeypatch.setattr(cg, "_asset_type_for", lambda wo: "article")       # all are draftable content
    monkeypatch.setattr(cg, "generate_for_wo",
                        lambda b, wo, biz, **k: called.append(wo["_db_id"]) or 999)

    cg.generate(bid, due_within_days=7)
    assert called == [due], f"JIT should draft only the near-due undrafted piece, drafted {called}"
    # every skip reason is exercised
    for skip in (far, drafted, done, gone):
        assert skip not in called
