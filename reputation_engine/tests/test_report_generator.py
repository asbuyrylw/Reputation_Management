"""Smoke test for report_generator.generate -- requires REP_TEST_DSN.

The report hub is otherwise untested. generate() makes NO LLM calls (the
narrative is templated Python; the optional timeline/acceleration/citation/
competitor sections are DB-only and individually try/except-wrapped inside
generate()), so this needs no LLM monkeypatching. matplotlib Agg is selected
inside report_generator._trend_chart() itself (matplotlib.use("Agg")), so no
headless setup is required here. We only redirect OUTPUT_DIR to a tmp dir so the
generated .docx is isolated and auto-cleaned by pytest's tmp_path.
"""

from __future__ import annotations

import os

from conftest import requires_db


def _seed_business(conn, name="Reportco LLC", contested="MLM,scam"):
    row = conn.execute(
        "INSERT INTO businesses (name, domain, services, goal, contested_terms, geo) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (name, "reportco.com", "insurance", "win local queries", contested, "Cincinnati OH"),
    ).fetchone()
    conn.commit()
    return row["id"]


def _complete_run(conn, bid, days_ago):
    """A finished+complete audit_run, dated `days_ago` in the past."""
    return conn.execute(
        "INSERT INTO audit_runs (business_id, finished_at, status) "
        "VALUES (%s, now() - make_interval(days => %s), 'complete') RETURNING id",
        (bid, days_ago),
    ).fetchone()["id"]


def _answer(conn, rid, bid, prompt, text, ga, contested, owned):
    conn.execute(
        "INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
        "goal_alignment,mentions_contested,surfaces_owned,failed) "
        "VALUES (%s,%s,'e',%s,%s,%s,%s,%s,false)",
        (rid, bid, prompt, text, ga, contested, owned),
    )


@requires_db
def test_generate_produces_nonempty_docx(fresh_schema, tmp_path, monkeypatch):
    conn = fresh_schema
    from rep_engine import report_generator as rg

    bid = _seed_business(conn)

    # Two COMPLETE runs sharing one prompt: baseline (weak) then improved (strong).
    # Two finished runs light up the trend chart, metrics table, and before/after
    # sections -- the most code-heavy branches of generate().
    prompt = "Is Reportco LLC trustworthy?"
    r1 = _complete_run(conn, bid, days_ago=30)
    r2 = _complete_run(conn, bid, days_ago=0)
    _answer(conn, r1, bid, prompt, "Some sources call Reportco an MLM.", 0.10, True, False)
    _answer(conn, r2, bid, prompt, "Reportco LLC is a trusted local insurance firm.", 0.80, False, True)
    conn.commit()

    # Isolate output so the .docx (and its temp chart PNG) never touch the repo's
    # ./output dir; tmp_path is auto-removed by pytest, so no manual cleanup.
    monkeypatch.setattr(rg, "OUTPUT_DIR", str(tmp_path))
    # Ensure no demo watermark branch is taken.
    monkeypatch.delenv("REP_REPORT_WATERMARK", raising=False)

    path = rg.generate(bid)

    # File was produced, lives under our tmp dir, and is non-empty.
    assert os.path.isfile(path)
    assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(str(tmp_path))
    assert os.path.getsize(path) > 0

    # Reopen the .docx and confirm key narrative content rendered.
    from docx import Document
    full_text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Reportco LLC" in full_text
    assert "Executive Summary" in full_text
