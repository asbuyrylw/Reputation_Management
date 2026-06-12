"""Tests for the offline scoring eval harness (eval_harness.py).

The agreement math is pure and tested with a fake judge (no key needed). The
live-judge regression test runs the real score_answer over the golden set and is
skipped automatically when no orchestrator key is configured.
"""

from __future__ import annotations

import csv
import json
import os

import pytest

from conftest import requires_db


def test_evaluate_computes_agreement():
    from rep_engine import eval_harness as ev
    golden = [
        {"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p1",
         "answer": {"text": "a", "sources": []},
         "expected": {"sentiment": "positive", "goal_alignment_min": 0.3, "goal_alignment_max": 1.0}},
        {"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p2",
         "answer": {"text": "b", "sources": []},
         "expected": {"sentiment": "negative", "goal_alignment_min": -1.0, "goal_alignment_max": 0.0}},
    ]

    def fake_score(business, prompt, ans):
        if prompt == "p1":
            return {"sentiment": "positive", "goal_alignment": 0.8}   # both correct
        return {"sentiment": "positive", "goal_alignment": -0.5}      # sentiment wrong, band ok

    rep = ev.evaluate(golden, score_fn=fake_score)
    assert rep["n"] == 2 and rep["scored"] == 2
    assert rep["sentiment_accuracy"] == 0.5         # case1 ok, case2 wrong
    assert rep["goal_alignment_band_rate"] == 1.0   # both within band


def test_evaluate_counts_unscored_as_miss():
    from rep_engine import eval_harness as ev
    golden = [{"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p",
               "answer": {"text": "a", "sources": []},
               "expected": {"sentiment": "positive", "goal_alignment_min": 0.0, "goal_alignment_max": 1.0}}]
    rep = ev.evaluate(golden, score_fn=lambda *args: {})   # judge produced nothing
    assert rep["scored"] == 0
    assert rep["sentiment_accuracy"] == 0.0 and rep["goal_alignment_band_rate"] == 0.0


def test_builtin_golden_set_is_well_formed():
    from rep_engine import eval_harness as ev
    assert len(ev.GOLDEN) >= 3
    for c in ev.GOLDEN:
        assert {"business", "prompt", "answer", "expected"} <= set(c)
        assert c["expected"]["sentiment"] in {"positive", "neutral", "negative", "mixed"}
        assert c["expected"]["goal_alignment_min"] <= c["expected"]["goal_alignment_max"]


_NO_KEY = ("YOUR_" in os.getenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY")
           and "YOUR_" in os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY"))


@pytest.mark.skipif(_NO_KEY, reason="no orchestrator API key set")
def test_live_scoring_meets_agreement_threshold():
    """Regression guard: with a real orchestrator key, the judge must agree with
    the golden labels above a threshold. Skipped automatically without a key."""
    from rep_engine import eval_harness as ev
    rep = ev.evaluate()
    assert rep["scored"] == rep["n"]              # the judge scored every case
    assert rep["sentiment_accuracy"] >= 0.66      # >= 2/3 sentiment agreement
    assert rep["goal_alignment_band_rate"] >= 0.66


# ---- golden-set file loader -----------------------------------------------------
def test_load_golden_falls_back_to_seed_when_absent(tmp_path):
    from rep_engine import eval_harness as ev
    assert ev.load_golden(str(tmp_path / "nope.jsonl")) == list(ev.GOLDEN)


def test_load_golden_reads_file_and_skips_malformed(tmp_path):
    from rep_engine import eval_harness as ev
    good = {"business": {"name": "X", "goal": "g", "contested_terms": ""}, "prompt": "p",
            "answer": {"text": "a", "sources": []},
            "expected": {"sentiment": "positive", "goal_alignment_min": 0.0, "goal_alignment_max": 1.0}}
    p = tmp_path / "g.jsonl"
    p.write_text(json.dumps(good) + "\n# a comment\n\n{not json}\n"
                 '{"prompt": "missing keys"}\n', encoding="utf-8")
    cases = ev.load_golden(str(p))
    assert len(cases) == 1 and cases[0]["prompt"] == "p"        # only the valid line survives


def test_load_golden_empty_file_falls_back_to_seed(tmp_path):
    from rep_engine import eval_harness as ev
    p = tmp_path / "empty.jsonl"
    p.write_text("# only comments, no cases\n", encoding="utf-8")
    assert ev.load_golden(str(p)) == list(ev.GOLDEN)


def test_shipped_golden_file_matches_seed():
    """The versioned eval_data/golden.jsonl must stay loadable + well-formed."""
    from rep_engine import eval_harness as ev
    cases = ev.load_golden(ev._default_golden_path())
    assert len(cases) >= len(ev.GOLDEN)
    assert all(ev._valid_case(c) for c in cases)


# ---- labeling-sheet round trip --------------------------------------------------
def test_ingest_sheet_keeps_only_valid_labeled_rows(tmp_path):
    from rep_engine import eval_harness as ev
    sheet = tmp_path / "sheet.csv"
    blank = {k: "" for k in ev._SHEET_FIELDS}
    with open(sheet, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ev._SHEET_FIELDS)
        w.writeheader()
        w.writerow({**blank, "business_name": "Acme", "goal": "trust", "contested_terms": "scam",
                    "prompt": "is acme legit?", "answer_text": "Yes, licensed.",
                    "sources": "acme.com | bbb.org", "label_sentiment": "positive",
                    "label_goal_alignment_min": "0.3", "label_goal_alignment_max": "1.0"})
        w.writerow({**blank, "prompt": "human hasn't labeled this yet"})          # skipped
        w.writerow({**blank, "prompt": "bad band", "label_sentiment": "negative",
                    "label_goal_alignment_min": "0.5", "label_goal_alignment_max": "0.1"})  # min>max -> skipped
    golden = tmp_path / "golden.jsonl"
    n = ev.ingest_labeling_sheet(str(sheet), golden_path=str(golden), append=False)
    assert n == 1
    cases = ev.load_golden(str(golden))
    assert len(cases) == 1
    c = cases[0]
    assert c["expected"] == {"sentiment": "positive", "goal_alignment_min": 0.3, "goal_alignment_max": 1.0}
    assert c["answer"]["sources"] == ["acme.com", "bbb.org"]
    assert c["business"]["name"] == "Acme"


def test_ingest_appends_to_existing_golden(tmp_path):
    from rep_engine import eval_harness as ev
    golden = tmp_path / "golden.jsonl"
    seed = {"business": {"name": "Seed", "goal": "g", "contested_terms": ""}, "prompt": "seed",
            "answer": {"text": "a", "sources": []},
            "expected": {"sentiment": "neutral", "goal_alignment_min": -0.1, "goal_alignment_max": 0.1}}
    golden.write_text(json.dumps(seed) + "\n", encoding="utf-8")
    sheet = tmp_path / "sheet.csv"
    blank = {k: "" for k in ev._SHEET_FIELDS}
    with open(sheet, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ev._SHEET_FIELDS)
        w.writeheader()
        w.writerow({**blank, "business_name": "Acme", "prompt": "p", "answer_text": "a",
                    "label_sentiment": "positive", "label_goal_alignment_min": "0.2",
                    "label_goal_alignment_max": "0.9"})
    ev.ingest_labeling_sheet(str(sheet), golden_path=str(golden), append=True)
    cases = ev.load_golden(str(golden))
    assert len(cases) == 2 and {c["prompt"] for c in cases} == {"seed", "p"}


def _one_row_sheet(path, fields):
    blank = {k: "" for k in fields}
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # utf-8-sig = with a BOM, as Excel saves
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({**blank, "business_name": "Acme", "prompt": "p", "answer_text": "a",
                    "label_sentiment": "positive", "label_goal_alignment_min": "0.2",
                    "label_goal_alignment_max": "0.9"})


def test_ingest_bare_filename_and_missing_trailing_newline(tmp_path, monkeypatch):
    """A bare --golden filename must not crash on makedirs(''), and appending to a file
    whose last line lacks a newline must not JOIN two cases onto one line."""
    from rep_engine import eval_harness as ev
    monkeypatch.chdir(tmp_path)
    seed = {"business": {"name": "S", "goal": "g", "contested_terms": ""}, "prompt": "seed",
            "answer": {"text": "a", "sources": []},
            "expected": {"sentiment": "neutral", "goal_alignment_min": -0.1, "goal_alignment_max": 0.1}}
    (tmp_path / "golden.jsonl").write_text(json.dumps(seed), encoding="utf-8")   # NO trailing newline
    _one_row_sheet(tmp_path / "sheet.csv", ev._SHEET_FIELDS)
    n = ev.ingest_labeling_sheet("sheet.csv", golden_path="golden.jsonl", append=True)   # bare names
    assert n == 1
    cases = ev.load_golden("golden.jsonl")
    assert len(cases) == 2 and {c["prompt"] for c in cases} == {"seed", "p"}   # both survive, not merged


def test_ingest_tolerates_excel_utf8_bom(tmp_path):
    """A sheet re-saved by Excel carries a UTF-8 BOM; the first column must not be lost."""
    from rep_engine import eval_harness as ev
    sheet = tmp_path / "sheet.csv"
    _one_row_sheet(sheet, ev._SHEET_FIELDS)
    golden = tmp_path / "golden.jsonl"
    ev.ingest_labeling_sheet(str(sheet), golden_path=str(golden), append=False)
    cases = ev.load_golden(str(golden))
    assert len(cases) == 1 and cases[0]["business"]["name"] == "Acme"   # name not eaten by the BOM


# ---- golden-case validation -----------------------------------------------------
def test_valid_case_rejects_bad_bands():
    from rep_engine import eval_harness as ev
    base = {"business": {}, "prompt": "p", "answer": {"text": "a"},
            "expected": {"sentiment": "positive", "goal_alignment_min": 0.0, "goal_alignment_max": 1.0}}
    assert ev._valid_case(base) is True
    bad = lambda exp: ev._valid_case({**base, "expected": exp})   # noqa: E731
    assert bad({"sentiment": "positive", "goal_alignment_min": 1.0, "goal_alignment_max": -1.0}) is False   # min>max
    assert bad({"sentiment": "positive", "goal_alignment_min": 5.0, "goal_alignment_max": 9.0}) is False    # out of range
    assert bad({"sentiment": "positive", "goal_alignment_min": True, "goal_alignment_max": False}) is False  # bool band
    assert bad({"sentiment": "wat", "goal_alignment_min": 0.0, "goal_alignment_max": 1.0}) is False          # bad sentiment


# ---- CSV formula-injection guard (pure, reversible) -----------------------------
def test_csv_guard_is_reversible():
    from rep_engine import eval_harness as ev
    for original in ["=cmd|calc", "+1", "-2", "@x", "'tis the season", "normal", "a=b", ""]:
        assert ev._csv_unquote(ev._csv_safe(original)) == original


# ---- CI gate --------------------------------------------------------------------
def test_gate_passes_fails_and_skips(monkeypatch):
    from rep_engine import eval_harness as ev
    monkeypatch.setattr(ev, "_has_orchestrator_key", lambda: True)   # exercise the scoring path

    def _rep(sent, band, scored=6):
        return {"n": 6, "scored": scored, "sentiment_accuracy": sent,
                "goal_alignment_band_rate": band, "details": []}

    monkeypatch.setattr(ev, "evaluate", lambda: _rep(0.9, 0.8))
    assert ev.gate(0.6, 0.6) == 0                       # both above floor -> pass
    monkeypatch.setattr(ev, "evaluate", lambda: _rep(0.5, 0.8))
    assert ev.gate(0.6, 0.6) == 1                       # sentiment below floor -> fail
    monkeypatch.setattr(ev, "evaluate", lambda: _rep(0.9, 0.4))
    assert ev.gate(0.6, 0.6) == 1                       # band below floor -> fail
    monkeypatch.setattr(ev, "evaluate", lambda: _rep(0.9, 0.9, scored=3))
    assert ev.gate(0.6, 0.6) == 0                       # partial scoring -> skip, not a spurious fail


def test_gate_skips_without_key_and_never_scores(monkeypatch):
    from rep_engine import eval_harness as ev
    monkeypatch.setattr(ev, "_has_orchestrator_key", lambda: False)

    def _boom():
        raise AssertionError("gate must not run the judge when there is no key")

    monkeypatch.setattr(ev, "evaluate", _boom)
    assert ev.gate(0.6, 0.6) == 0                       # skip BEFORE any scoring / HTTP


def test_has_orchestrator_key_treats_empty_as_missing(monkeypatch):
    from rep_engine import eval_harness as ev
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")        # how GitHub expands an UNSET secret
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert ev._has_orchestrator_key() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    assert ev._has_orchestrator_key() is True


# ---- export from real answers (DB) ----------------------------------------------
@requires_db
def test_export_labeling_sheet_prefills_judge_guess(fresh_schema, tmp_path):
    conn = fresh_schema
    from rep_engine import eval_harness as ev
    bid = conn.execute("INSERT INTO businesses (name, goal, contested_terms) "
                       "VALUES ('Acme','trust','scam') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, status) VALUES (%s,'complete') "
                       "RETURNING id", (bid,)).fetchone()["id"]
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,cited_sources,"
                 "sentiment,goal_alignment,mentions_contested,failed) "
                 "VALUES (%s,%s,'chatgpt','is acme legit?','Yes, licensed.',%s,'positive',0.7,false,false)",
                 (rid, bid, json.dumps(["acme.com"])))
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,failed) "
                 "VALUES (%s,%s,'chatgpt','x','y',true)", (rid, bid))   # failed -> excluded
    conn.commit()
    out = tmp_path / "sheet.csv"
    n = ev.export_labeling_sheet(str(out), business_id=bid, limit=50)
    assert n == 1                                        # the failed row is excluded
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 1
    r = rows[0]
    assert r["judge_sentiment"] == "positive"           # prefilled from the stored audit score
    assert r["judge_goal_alignment"] == "0.70"
    assert r["sources"] == "acme.com"
    assert r["label_sentiment"] == "" and r["label_goal_alignment_min"] == ""   # blank for the human


@requires_db
def test_export_neutralizes_csv_formula_injection(fresh_schema, tmp_path):
    """A scraped answer beginning with '=' must not be written as a live formula; the
    guard prefixes a quote on export and ingest strips it back (lossless round trip)."""
    conn = fresh_schema
    from rep_engine import eval_harness as ev
    bid = conn.execute("INSERT INTO businesses (name, goal, contested_terms) "
                       "VALUES ('Acme','trust','scam') RETURNING id").fetchone()["id"]
    rid = conn.execute("INSERT INTO audit_runs (business_id, status) VALUES (%s,'complete') "
                       "RETURNING id", (bid,)).fetchone()["id"]
    payload = '=cmd|/c calc!A1 says acme is a scam'
    conn.execute("INSERT INTO answers (run_id,business_id,engine,prompt,answer_text,"
                 "sentiment,goal_alignment,failed) "
                 "VALUES (%s,%s,'chatgpt','q',%s,'negative',-0.5,false)", (rid, bid, payload))
    conn.commit()
    out = tmp_path / "sheet.csv"
    ev.export_labeling_sheet(str(out), business_id=bid)
    raw = open(out, encoding="utf-8").read()
    assert "\n'=cmd" in raw or ",'=cmd" in raw          # quote-guarded in the file, not a live "=" cell
    # a human labels it, then ingest recovers the ORIGINAL text (quote stripped)
    row = next(csv.DictReader(open(out, encoding="utf-8")))
    row.update(label_sentiment="negative", label_goal_alignment_min="-1.0",
               label_goal_alignment_max="-0.2")
    case = ev._sheet_row_to_case(row)
    assert case["answer"]["text"] == payload            # lossless
