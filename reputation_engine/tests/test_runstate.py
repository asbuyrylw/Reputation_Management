"""Resumable run-state tests -- require REP_TEST_DSN."""

from __future__ import annotations

import pytest
from conftest import requires_db


@requires_db
def test_step_runs_once_and_records_done(fresh_schema):
    conn = fresh_schema
    from rep_engine import runstate as rs
    bid = conn.execute("INSERT INTO businesses (name, domain, goal) VALUES ('A','a.com','g') RETURNING id").fetchone()["id"]
    conn.commit()
    calls = []
    r = rs.RunState.start(bid, kind="cycle", resume=False)
    r.step("audit", lambda: calls.append("audit"))
    r.step("report", lambda: calls.append("report"))
    r.finish()
    assert calls == ["audit", "report"]
    row = conn.execute("SELECT status FROM pipeline_runs WHERE id=%s", (r.run_id,)).fetchone()
    assert row["status"] == "complete"
    done = conn.execute("SELECT COUNT(*) n FROM pipeline_steps WHERE pipeline_run_id=%s AND status='done'",
                        (r.run_id,)).fetchone()["n"]
    assert done == 2


@requires_db
def test_resume_skips_completed_steps(fresh_schema):
    conn = fresh_schema
    from rep_engine import runstate as rs
    bid = conn.execute("INSERT INTO businesses (name, domain, goal) VALUES ('B','b.com','g') RETURNING id").fetchone()["id"]
    conn.commit()

    # first attempt: audit succeeds, gap_model raises
    r1 = rs.RunState.start(bid, kind="cycle", resume=False)
    r1.step("audit", lambda: None)
    with pytest.raises(RuntimeError):
        def boom():
            raise RuntimeError("transient API failure")
        r1.step("gap_model", boom)
    # run marked failed, audit done, gap_model failed
    run_status = conn.execute("SELECT status FROM pipeline_runs WHERE id=%s", (r1.run_id,)).fetchone()["status"]
    assert run_status == "failed"

    # resume: should reuse the SAME run, skip audit, re-run gap_model + report
    ran = []
    r2 = rs.RunState.start(bid, kind="cycle", resume=True)
    assert r2.run_id == r1.run_id          # resumed same run
    r2.step("audit", lambda: ran.append("audit"))   # should be skipped
    r2.step("gap_model", lambda: ran.append("gap_model"))
    r2.step("report", lambda: ran.append("report"))
    r2.finish()
    assert "audit" not in ran               # skipped because already done
    assert ran == ["gap_model", "report"]
    assert conn.execute("SELECT status FROM pipeline_runs WHERE id=%s", (r1.run_id,)).fetchone()["status"] == "complete"


@requires_db
def test_failed_step_is_resumable_not_lost(fresh_schema):
    conn = fresh_schema
    from rep_engine import runstate as rs
    bid = conn.execute("INSERT INTO businesses (name, domain, goal) VALUES ('C','c.com','g') RETURNING id").fetchone()["id"]
    conn.commit()
    r = rs.RunState.start(bid, kind="cycle", resume=False)
    r.step("audit", lambda: None)
    with pytest.raises(ValueError):
        def boom():
            raise ValueError("budget exceeded mid-run")
        r.step("citation", boom)
    # the failed step records the error for diagnosis
    row = conn.execute("SELECT status, error FROM pipeline_steps WHERE pipeline_run_id=%s AND step_key='citation'",
                       (r.run_id,)).fetchone()
    assert row["status"] == "failed"
    assert "budget" in row["error"]


@requires_db
def test_new_run_when_resume_false(fresh_schema):
    conn = fresh_schema
    from rep_engine import runstate as rs
    bid = conn.execute("INSERT INTO businesses (name, domain, goal) VALUES ('D','d.com','g') RETURNING id").fetchone()["id"]
    conn.commit()
    r1 = rs.RunState.start(bid, kind="cycle", resume=False)
    r1.step("audit", lambda: None)
    # finish so it's not in_progress, then a fresh start makes a NEW run
    r1.finish()
    r2 = rs.RunState.start(bid, kind="cycle", resume=False)
    assert r2.run_id != r1.run_id
