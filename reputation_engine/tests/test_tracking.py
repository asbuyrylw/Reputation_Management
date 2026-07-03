"""Execution tracking: manual work-order creation."""

from __future__ import annotations

from conftest import requires_db


@requires_db
def test_create_manual_work_order(fresh_schema):
    conn = fresh_schema
    from rep_engine import tracking as t
    bid = conn.execute("INSERT INTO businesses (name) VALUES ('Acme') RETURNING id").fetchone()["id"]
    conn.commit()

    t.create_work_order(bid, "Publish licensing page", instruction="Write the page",
                        recommended_tool="CMS", target_date="2026-07-01")
    t.create_work_order(bid, "Get 5 Google reviews")

    rows = conn.execute(
        "SELECT wo_code, title, status, phase, plan_id, target_date FROM work_orders "
        "WHERE business_id=%s ORDER BY id", (bid,),
    ).fetchall()
    assert len(rows) == 2
    # per-business MANUAL-<n> codes, no plan, tracked as a pending manual task
    assert rows[0]["wo_code"] == "MANUAL-1" and rows[1]["wo_code"] == "MANUAL-2"
    assert rows[0]["status"] == "pending" and rows[0]["phase"] == "manual"
    assert rows[0]["plan_id"] is None
    assert str(rows[0]["target_date"]) == "2026-07-01"
    assert {r["title"] for r in rows} == {"Publish licensing page", "Get 5 Google reviews"}
