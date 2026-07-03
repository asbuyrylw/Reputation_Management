# Eval golden set — how to grow it

The scoring **judge** (`ai_state_audit.score_answer`) produces the two headline
metrics — **sentiment** and **goal_alignment** — for every AI answer. Those numbers
drive the gap model, the report, the timeline, and incident severity, but the judge
itself is only as trustworthy as the cases we check it against. `golden.jsonl` is
that check: a set of real answers with **human** labels. The bigger and more
realistic it is, the more confidently CI can catch a prompt tweak or model swap that
silently degrades scoring.

- `golden.jsonl` — the golden set (one JSON case per line). Loaded by
  `eval_harness.load_golden()`. The 6 seed cases ship here; **append real labeled
  cases to grow it.**
- `labeling_sheet_template.csv` — an empty sheet you can fill by hand.

## The fastest path — label real audit answers

```bash
# 1) Export real, non-failed answers into a CSV, PREFILLED with the judge's current
#    guess (judge_sentiment / judge_goal_alignment). No LLM calls — it reads the
#    scores already stored from past audits. Hardest cases (contested / low-alignment)
#    are listed first. Point it at the DB that holds real audits (REP_DB_DSN).
python -m rep_engine.eval_harness export --out sheet.csv [--business-id N] [--limit 50]

# 2) A human fills three columns per row:
#       label_sentiment            -> one of: positive | negative | neutral | mixed
#       label_goal_alignment_min   -> a number in [-1, 1]   (band low)
#       label_goal_alignment_max   -> a number in [-1, 1]   (band high, >= min)
#    Use a RANGE, not a point: "this answer should score between +0.3 and +1.0".
#    Leave a row's label_* blank to skip it; partially-labeled sheets are fine.

# 3) Ingest the filled rows into golden.jsonl (append by default).
python -m rep_engine.eval_harness ingest --sheet sheet.csv

# 4) Measure agreement, and/or gate CI (needs an orchestrator key; skips without one).
python -m rep_engine.eval_harness run
python -m rep_engine.eval_harness gate --min-sentiment 0.6 --min-band 0.6
```

`judge_sentiment` / `judge_goal_alignment` are only a hint — the engine's current
guess. Your job is to fill `label_*` with the *correct* answer; where they differ is
exactly where the judge is weak and the eval earns its keep.

## A worked example (one filled row)

| column | value |
| --- | --- |
| business_name | Acme Insurance |
| goal | be seen as a trusted local insurance advisor |
| contested_terms | MLM,scam |
| engine | chatgpt |
| prompt | Is Acme Insurance an MLM? |
| answer_text | Several forum posts describe Acme as a multi-level marketing scheme... |
| sources | reddit.com/r/antimlm \| complaintsboard.com |
| judge_sentiment | negative |
| judge_goal_alignment | -0.40 |
| **label_sentiment** | **negative** |
| **label_goal_alignment_min** | **-1.0** |
| **label_goal_alignment_max** | **-0.2** |
| notes | clearly off-goal; band stays negative |

## Where to focus labeling

The easy positive/negative cases are already covered. The judge drifts most on:
**mixed** answers, **contested-but-accurate** answers, **sarcasm**, **thin/empty**
answers, answers that **name a competitor**, very **long** answers, and **non-English**
text. ~30–50 cases makes a usable guard; 100+ to trust the band rates. Raise the
`gate` floors as the set grows past the seed cases.
