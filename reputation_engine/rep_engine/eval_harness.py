"""
Reputation Crowding-Out Engine -- Offline scoring eval (regression guard)
========================================================================
The product's headline metrics -- sentiment and goal_alignment -- come from an
LLM "judge" (ai_state_audit.score_answer) that is otherwise unvalidated against
ground truth. A prompt tweak, a model swap (e.g. routing scoring to the cheap
Haiku tier), or a provider change could silently degrade scoring and no test
would notice.

This harness runs the judge over a small GOLDEN set of (answer -> expected
human label) cases and reports agreement (sentiment accuracy + goal_alignment
band rate), so a regression is caught before it ships. It is intentionally
dependency-free; a heavier LLM-as-judge framework (deepeval / promptfoo / ragas)
can be layered on the same GOLDEN set later.

Grow the golden set with real labeled examples -- the signal scales with size. The
set lives in a versioned data file (eval_data/golden.jsonl) so non-engineers can add
cases without touching code; the inline GOLDEN below is the built-in seed/fallback.
The live judge needs an orchestrator key; the agreement math is pure and unit-tested.

Workflow to grow it from REAL audits (no LLM spend until `gate`/`run`):
    # 1. export real answers into a CSV, prefilled with the judge's current guess
    python -m rep_engine.eval_harness export --out sheet.csv [--business-id N] [--limit 50]
    # 2. a human fills the label_sentiment / label_goal_alignment_min/max columns
    # 3. ingest the filled rows into the golden set
    python -m rep_engine.eval_harness ingest --sheet sheet.csv
    # 4. measure agreement / gate CI (live judge; skips cleanly without a key)
    python -m rep_engine.eval_harness run
    python -m rep_engine.eval_harness gate --min-sentiment 0.6 --min-band 0.6
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

try:
    from . import ai_state_audit as a
except ImportError:  # pragma: no cover
    import ai_state_audit as a  # type: ignore

log = logging.getLogger("eval_harness")

# Valid human-label sentiment values (the judge's label space).
_SENTIMENTS = ("positive", "negative", "neutral", "mixed")

# Seed golden set. Each case: a business context, a prompt, a (text, sources)
# answer, and the expected human label (sentiment + a goal_alignment band).
# EXPAND with real labeled examples -- this is a starting point, not a benchmark.
GOLDEN: list[dict] = [
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "Is Team Unstoppable a legitimate life-insurance business?",
        "answer": {"text": "Team Unstoppable is a licensed life-insurance agency with "
                           "strong local reviews and clear disclosures.",
                   "sources": ["teamunstoppable.com"]},
        "expected": {"sentiment": "positive", "goal_alignment_min": 0.3, "goal_alignment_max": 1.0},
    },
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "Is Team Unstoppable an MLM scam?",
        "answer": {"text": "Several forum posts call Team Unstoppable an MLM pyramid "
                           "scheme to avoid.",
                   "sources": ["reddit.com/r/antimlm"]},
        "expected": {"sentiment": "negative", "goal_alignment_min": -1.0, "goal_alignment_max": -0.1},
    },
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "What does Team Unstoppable do?",
        "answer": {"text": "Team Unstoppable appears to be a company; details are limited.",
                   "sources": []},
        "expected": {"sentiment": "neutral", "goal_alignment_min": -0.2, "goal_alignment_max": 0.3},
    },
    {
        "business": {"name": "Team Unstoppable",
                     "goal": "be seen as a trusted local life-insurance advisor",
                     "contested_terms": "MLM,pyramid scheme,scam"},
        "prompt": "Should I work with Team Unstoppable?",
        "answer": {"text": "Team Unstoppable is a licensed agency with good client reviews, though "
                           "some online forums question its multi-level recruiting model.",
                   "sources": ["teamunstoppable.com", "reddit.com/r/antimlm"]},
        "expected": {"sentiment": "mixed", "goal_alignment_min": -0.3, "goal_alignment_max": 0.3},
    },
    {
        "business": {"name": "Dr. Lena Ortiz",
                     "goal": "be recognized as a leading pediatric dentist in Austin",
                     "contested_terms": "malpractice,fraud"},
        "prompt": "Who is a top pediatric dentist in Austin?",
        "answer": {"text": "Dr. Lena Ortiz is a board-certified pediatric dentist in Austin with "
                           "excellent patient ratings and hospital affiliations.",
                   "sources": ["lenaortizdds.com", "healthgrades.com"]},
        "expected": {"sentiment": "positive", "goal_alignment_min": 0.5, "goal_alignment_max": 1.0},
    },
    {
        "business": {"name": "Dr. Lena Ortiz",
                     "goal": "be recognized as a leading pediatric dentist in Austin",
                     "contested_terms": "malpractice,fraud"},
        "prompt": "Has Dr. Lena Ortiz had any malpractice issues?",
        "answer": {"text": "Several consumer review sites describe malpractice complaints against "
                           "Dr. Ortiz and advise caution.",
                   "sources": ["ratemds.com", "complaintsboard.com"]},
        "expected": {"sentiment": "negative", "goal_alignment_min": -1.0, "goal_alignment_max": -0.2},
    },
]


# ----------------------------------------------------------------------------
# Golden-set storage -- a versioned data file so NON-engineers can grow the set
# without editing code. The inline GOLDEN above is the built-in SEED / fallback;
# the file (eval_data/golden.jsonl) is the primary store once it exists.
# ----------------------------------------------------------------------------
def _default_golden_path() -> str:
    # eval_harness.py lives in rep_engine/; the data file sits at the package root.
    return str(Path(__file__).resolve().parents[1] / "eval_data" / "golden.jsonl")


def _valid_case(c) -> bool:
    if not isinstance(c, dict):
        return False
    exp = c.get("expected")
    ans = c.get("answer")
    if not (isinstance(c.get("business"), dict) and isinstance(c.get("prompt"), str)
            and isinstance(ans, dict) and isinstance(ans.get("text"), str)
            and isinstance(exp, dict) and exp.get("sentiment") in _SENTIMENTS):
        return False
    lo, hi = exp.get("goal_alignment_min"), exp.get("goal_alignment_max")
    # bool is a subclass of int -- reject it so True/False can't pose as a band value.
    if isinstance(lo, bool) or isinstance(hi, bool):
        return False
    if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
        return False
    return -1.0 <= lo <= hi <= 1.0          # same band invariant the ingest path enforces


def load_golden(path: Optional[str] = None) -> list:
    """Load the golden set from a JSONL file (one case per line; blank/`#` lines
    skipped). Falls back to the built-in seed GOLDEN when the file is absent or has
    no valid cases, so the harness never breaks. Malformed lines are skipped + warned."""
    path = path or os.getenv("EVAL_GOLDEN_PATH") or _default_golden_path()
    if not os.path.exists(path):
        log.info("eval: golden file %s not found -- using built-in seed set (%d cases)",
                 path, len(GOLDEN))
        return list(GOLDEN)
    cases = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as e:
                log.warning("eval golden line %d: bad JSON (%s) -- skipped", i, e)
                continue
            if _valid_case(c):
                cases.append(c)
            else:
                log.warning("eval golden line %d: missing/invalid keys -- skipped", i)
    if not cases:
        log.warning("eval: %s had no valid cases -- using built-in seed set", path)
        return list(GOLDEN)
    return cases


def evaluate(golden: Optional[list] = None,
             score_fn: Optional[Callable[[dict, str, dict], dict]] = None) -> dict:
    """Run the scoring judge over `golden` and report agreement with the labels.

    `score_fn(business, prompt, answer) -> score dict` defaults to the live
    ai_state_audit.score_answer; inject a fake for testing. A case the judge
    could not score (empty/None result -> sentiment or goal_alignment missing) is
    counted as unscored, never as agreement. With no explicit `golden`, the set is
    loaded from the versioned file (load_golden), falling back to the seed set."""
    golden = load_golden() if golden is None else golden
    score_fn = score_fn or a.score_answer
    n = len(golden)
    sentiment_hits = band_hits = scored = 0
    details = []
    for case in golden:
        s = score_fn(case["business"], case["prompt"], case["answer"]) or {}
        exp = case["expected"]
        got_sent = s.get("sentiment")
        got_ga = s.get("goal_alignment")
        is_scored = got_sent is not None and got_ga is not None
        sent_ok = bool(is_scored and got_sent == exp["sentiment"])
        band_ok = bool(is_scored
                       and exp["goal_alignment_min"] <= float(got_ga) <= exp["goal_alignment_max"])
        scored += int(is_scored)
        sentiment_hits += int(sent_ok)
        band_hits += int(band_ok)
        details.append({"prompt": case["prompt"], "expected": exp,
                        "got_sentiment": got_sent, "got_goal_alignment": got_ga,
                        "sentiment_ok": sent_ok, "band_ok": band_ok})
    return {
        "n": n,
        "scored": scored,
        "sentiment_accuracy": (sentiment_hits / n) if n else 0.0,
        "goal_alignment_band_rate": (band_hits / n) if n else 0.0,
        "details": details,
    }


# ----------------------------------------------------------------------------
# Labeling-sheet round-trip: export REAL audit answers -> human labels -> golden
# ----------------------------------------------------------------------------
# The CSV a human fills in. judge_* are the engine's CURRENT guess (the stored
# audit score -- NO new LLM call); the human fills the label_* columns.
_SHEET_FIELDS = [
    "business_name", "goal", "contested_terms", "engine", "prompt", "answer_text",
    "sources", "judge_sentiment", "judge_goal_alignment",
    "label_sentiment", "label_goal_alignment_min", "label_goal_alignment_max", "notes",
]

# CSV formula-injection guard: answer_text / prompt / sources are SCRAPED, attacker-
# influenceable content, and a spreadsheet treats a cell starting with = + - @ (or a
# leading tab/CR) as a formula. Prefix such cells with a single quote on export;
# strip exactly one leading quote on ingest so the round trip is lossless.
_CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(v) -> str:
    s = "" if v is None else str(v)
    # Also quote a value that ALREADY starts with "'" so _csv_unquote (which always
    # strips one leading quote) is exactly reversible -- otherwise "'tis" -> "tis".
    return "'" + s if (s[:1] in _CSV_RISKY or s[:1] == "'") else s


def _csv_unquote(v) -> str:
    s = "" if v is None else str(v)
    return s[1:] if s[:1] == "'" else s


def export_labeling_sheet(out_path: str, *, business_id: Optional[int] = None,
                          limit: int = 50) -> int:
    """Pull REAL, non-failed audit answers into a CSV labeling sheet, PREFILLED with
    the judge's current stored guess (judge_sentiment / judge_goal_alignment) so a
    human only confirms or corrects the label_* columns. No LLM calls. Returns the
    number of rows written. Prefers the hardest cases to label: contested or
    low-alignment answers first."""
    try:
        from .db import db
    except ImportError:  # pragma: no cover
        from db import db  # type: ignore
    where = "a.failed = false AND a.answer_text IS NOT NULL AND a.answer_text <> ''"
    params: list = []
    if business_id is not None:
        where += " AND a.business_id = %s"
        params.append(business_id)
    params.append(limit)
    with db() as conn:
        # `where` is a hardcoded literal plus an optional " AND a.business_id = %s"
        # fragment; the value is bound through `params`. No user input is interpolated
        # into the SQL string. # nosec B608
        rows = conn.execute(
            f"""SELECT b.name AS business_name, b.goal, b.contested_terms,
                       a.engine, a.prompt, a.answer_text, a.cited_sources,
                       a.sentiment, a.goal_alignment, a.mentions_contested
                FROM answers a JOIN businesses b ON b.id = a.business_id
                WHERE {where}
                ORDER BY a.mentions_contested DESC NULLS LAST,
                         a.goal_alignment ASC NULLS LAST, a.id DESC
                LIMIT %s""", params).fetchall()  # nosec B608
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_SHEET_FIELDS)
        w.writeheader()
        for r in rows:
            src = r.get("cited_sources")
            sources = " | ".join(str(s) for s in src) if isinstance(src, list) else ""
            w.writerow({
                # free-text, scraped-content cells go through the formula-injection guard.
                "business_name": _csv_safe(r.get("business_name")),
                "goal": _csv_safe(r.get("goal")),
                "contested_terms": _csv_safe(r.get("contested_terms")),
                "engine": _csv_safe(r.get("engine")),
                "prompt": _csv_safe(r.get("prompt")),
                "answer_text": _csv_safe(r.get("answer_text")),
                "sources": _csv_safe(sources),
                "judge_sentiment": r.get("sentiment") or "",
                "judge_goal_alignment": r.get("goal_alignment") if r.get("goal_alignment") is not None else "",
                # human fills these; pre-seed the band from the judge's guess as a hint.
                "label_sentiment": "", "label_goal_alignment_min": "",
                "label_goal_alignment_max": "", "notes": "",
            })
    return len(rows)


def _sheet_row_to_case(row: dict) -> Optional[dict]:
    """Convert ONE filled sheet row into a golden case, or None (+warn) if the human
    labels are missing/invalid. A row is only ingested once a human has supplied a
    valid sentiment AND a numeric [min,max] band with min<=max in [-1,1]."""
    sent = (row.get("label_sentiment") or "").strip().lower()
    if sent not in _SENTIMENTS:
        return None
    try:
        lo = float(row.get("label_goal_alignment_min"))
        hi = float(row.get("label_goal_alignment_max"))
    except (TypeError, ValueError):
        return None
    if not (-1.0 <= lo <= hi <= 1.0):
        log.warning("ingest: row %r has an invalid band [%s,%s] -- skipped",
                    (row.get("prompt") or "")[:40], lo, hi)
        return None
    # undo the export-time CSV formula-injection guard (one leading quote, if any).
    sources = [s.strip() for s in _csv_unquote(row.get("sources")).split("|") if s.strip()]
    return {
        "business": {"name": _csv_unquote(row.get("business_name")),
                     "goal": _csv_unquote(row.get("goal")),
                     "contested_terms": _csv_unquote(row.get("contested_terms"))},
        "prompt": _csv_unquote(row.get("prompt")),
        "answer": {"text": _csv_unquote(row.get("answer_text")), "sources": sources},
        "expected": {"sentiment": sent, "goal_alignment_min": lo, "goal_alignment_max": hi},
    }


def ingest_labeling_sheet(sheet_path: str, *, golden_path: Optional[str] = None,
                          append: bool = True) -> int:
    """Read a filled labeling CSV and write the valid, human-labeled rows into the
    golden JSONL (append by default, else overwrite). Returns the count ingested.
    Rows without valid human labels are skipped, so a partially-labeled sheet is fine."""
    golden_path = golden_path or _default_golden_path()
    # utf-8-sig transparently strips a BOM if the human re-saved the sheet from Excel
    # (plain utf-8 would mangle the first header into '﻿business_name').
    with open(sheet_path, encoding="utf-8-sig", newline="") as f:
        cases = [c for c in (_sheet_row_to_case(r) for r in csv.DictReader(f)) if c]
    d = os.path.dirname(golden_path)
    if d:                                    # a bare filename -> dirname "" -> makedirs("") raises
        os.makedirs(d, exist_ok=True)
    # Appending to a file whose last line lacks a trailing newline would JOIN the last
    # existing case to the first new one on one physical line (json.loads then drops BOTH).
    if append and os.path.exists(golden_path) and os.path.getsize(golden_path) > 0:
        with open(golden_path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            missing_nl = f.read(1) != b"\n"
        if missing_nl:
            with open(golden_path, "a", encoding="utf-8") as f:
                f.write("\n")
    mode = "a" if append else "w"
    with open(golden_path, mode, encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    log.info("ingest: wrote %d labeled case(s) -> %s (%s)", len(cases), golden_path,
             "append" if append else "overwrite")
    return len(cases)


def _has_orchestrator_key() -> bool:
    """True only if a USABLE orchestrator key is configured. An empty env var (how
    GitHub expands an unset secret) counts as no key, so the gate never fires real
    HTTP in a keyless CI."""
    def _usable(name: str, placeholder: str) -> bool:
        v = os.getenv(name, placeholder)
        return bool(v) and "YOUR_" not in v
    return _usable("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY") or \
        _usable("OPENAI_API_KEY", "YOUR_OPENAI_KEY")


def gate(min_sentiment: float = 0.6, min_band: float = 0.6) -> int:
    """CI regression gate: run the live judge over the golden set and return a
    process exit code -- 0 pass, 1 fail. SKIPS (returns 0, no HTTP) when no usable
    orchestrator key is set, and SKIPS when the judge couldn't score every case
    (transient availability must not masquerade as a regression). Safe to always wire in."""
    if not _has_orchestrator_key():
        print("eval gate: no usable orchestrator key -- SKIPPING (not a failure).")
        return 0
    rep = evaluate()
    print(f"eval gate: {rep['scored']}/{rep['n']} scored | "
          f"sentiment {rep['sentiment_accuracy']:.2f} (floor {min_sentiment:.2f}) | "
          f"band {rep['goal_alignment_band_rate']:.2f} (floor {min_band:.2f})")
    if rep["scored"] < rep["n"]:
        print(f"eval gate: only {rep['scored']}/{rep['n']} scored -- SKIPPING "
              "(insufficient availability to judge a regression).")
        return 0
    ok = (rep["sentiment_accuracy"] >= min_sentiment
          and rep["goal_alignment_band_rate"] >= min_band)
    print("eval gate: PASS" if ok else "eval gate: FAIL -- scoring regressed below the floor")
    return 0 if ok else 1


def _print_report(rep: dict) -> None:
    print(f"Scoring eval over {rep['n']} golden case(s) ({rep['scored']} scored):")
    print(f"  sentiment accuracy:        {rep['sentiment_accuracy']:.2f}")
    print(f"  goal_alignment band rate:  {rep['goal_alignment_band_rate']:.2f}")
    for d in rep["details"]:
        mark = "ok  " if (d["sentiment_ok"] and d["band_ok"]) else "DIFF"
        print(f"  [{mark}] {d['prompt'][:48]:48} -> sent={d['got_sentiment']} "
              f"ga={d['got_goal_alignment']}")
    if rep["scored"] == 0:
        print("\nNo cases scored -- set an orchestrator key (e.g. ANTHROPIC_API_KEY) "
              "to run the judge.")


def main() -> None:
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Scoring-judge eval harness + golden-set tools")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("run", help="run the judge over the golden set and report agreement")

    pe = sub.add_parser("export", help="export real audit answers into a CSV labeling sheet")
    pe.add_argument("--out", required=True, help="path to write the CSV labeling sheet")
    pe.add_argument("--business-id", type=int, default=None)
    pe.add_argument("--limit", type=int, default=50)

    pi = sub.add_parser("ingest", help="ingest a filled labeling sheet into golden.jsonl")
    pi.add_argument("--sheet", required=True, help="path to the filled CSV labeling sheet")
    pi.add_argument("--golden", default=None, help="golden.jsonl path (default: eval_data/golden.jsonl)")
    pi.add_argument("--overwrite", action="store_true", help="overwrite golden instead of appending")

    pg = sub.add_parser("gate", help="CI regression gate (exit 1 if below the floor)")
    pg.add_argument("--min-sentiment", type=float, default=0.6)
    pg.add_argument("--min-band", type=float, default=0.6)

    args = ap.parse_args()
    cmd = args.cmd or "run"
    if cmd == "run":
        _print_report(evaluate())
    elif cmd == "export":
        n = export_labeling_sheet(args.out, business_id=args.business_id, limit=args.limit)
        print(f"Wrote {n} row(s) to {args.out}. Fill the label_* columns, then: "
              f"python -m rep_engine.eval_harness ingest --sheet {args.out}")
    elif cmd == "ingest":
        n = ingest_labeling_sheet(args.sheet, golden_path=args.golden, append=not args.overwrite)
        print(f"Ingested {n} labeled case(s) into the golden set.")
    elif cmd == "gate":
        sys.exit(gate(min_sentiment=args.min_sentiment, min_band=args.min_band))


if __name__ == "__main__":
    main()
