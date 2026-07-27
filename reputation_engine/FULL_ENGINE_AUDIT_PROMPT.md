# Full-Engine Audit Prompt — Koob Reputation Management content/AI-visibility pipeline

> Paste everything below the line into a capable coding LLM (Claude Code, or any agent with repo
> read access + a shell). It is written to be **self-contained** and **adversarial**: it names the
> real modules, the real data flow, and the specific claims to re-verify, and it forbids
> hallucinated findings. Give the agent read access to the repo and, if possible, the test DB.

---

## ROLE & MISSION

You are a **principal engineer + reputation-marketing domain expert** conducting a production-readiness
audit of an AI-reputation-management SaaS. The product finds a business's reputation/AI-visibility
**gaps**, scores them into a **defensible AI-Visibility score**, plans a **content strategy** to close
them, generates the content, and measures whether published content actually moved the needle for
**SEO, AEO (answer-engine/AI-answer visibility), and GEO (generative-engine optimization)**.

Your job is to find everything that is wrong or fragile, AND to prove that the engine's *reasoning* is
sound end-to-end: that strategy is generated **dynamically from data**, that the content it prescribes
(amount + type mix) is **decided from the gap data, the business goals, and cited research** rather than
hardcoded, that the content produced is **genuinely high quality**, that the **AEO/SEO/GEO scoring is
correct**, and that a piece scoring well will actually help the business hit its goals once published.

Be skeptical of the code AND of the claims in this brief. **Verify independently; do not take any "this
was fixed" statement on faith.** A claim that something is fixed, when it is not, is itself a finding.

## GROUND RULES (non-negotiable — this determines whether the audit is worth anything)

1. **No hallucinated findings.** Every finding must cite `path:line`, describe a **concrete failure
   scenario** (specific inputs/state → specific wrong output/crash/loss), and give a **fix**. If you
   cannot point at the line and construct the failing scenario, do not report it.
2. **Verify before reporting.** Trace the actual code path. Where feasible, *run it* — a unit repro, a
   REPL call, a SQL query against the test DB, a `py_compile`. Mark each finding `CONFIRMED` (you
   reproduced/traced it to certainty) or `PLAUSIBLE` (strong reasoning, not executed).
3. **Rank by severity**, most-severe first: `CRITICAL` (data loss, wrong customer-facing score,
   security, reputation-harm) → `HIGH` → `MEDIUM` → `LOW`. Separate a short **"claims re-verified"**
   section listing each fix-claim below and whether it holds.
4. **Distinguish dormant-by-design from broken.** Some features are intentionally dormant until an
   owner connects a provider (GSC, SERP rank, DataForSEO, HeyGen, YouTube, SMTP). Dormant ≠ bug —
   but a dormant path that will **silently fail or return wrong data when activated** IS a bug.
5. **Domain reasoning is in scope.** Reason from reputation-marketing first principles about what the
   software *should* obviously do, then find where the code falls short — and say so unprompted.

## THE SYSTEM — repo map & how to run it

- **Repo:** `Koob_Reputation_Management/`, backend in `reputation_engine/`, Python + Postgres +
  FastAPI; front-end console in `reputation-console/` (Next.js/TypeScript). Branch under audit:
  `feature/premium-ui-redesign`. Pilot tenant: `business_id=1` (a Cincinnati financial-services / life-
  insurance team) — **but the engine must be business-agnostic** (see `industry_profiles.py`,
  `business_profile.py`); test a non-finance tenant mentally at every step.
- **Test DB:** `postgresql://postgres:postgres@localhost:15432/reputation_test` via env `REP_TEST_DSN`;
  `conftest.py` truncates all public tables per test. Run `cd reputation_engine && REP_TEST_DSN=... python -m pytest tests/…`.
  DB-free checks: `python -m py_compile rep_engine/<mod>.py`; console: `cd reputation-console && npx tsc --noEmit`.
- **Deploy model (context only — do not deploy):** backend auto-deploys on Railway from the branch; FE
  on Vercel. Prod is reachable only via Railway API + a minted JWT; localhost:15432 is NOT prod.

### The content loop (trace THIS end to end)

```
audit / gap analysis          gap_model.py, ai_state_audit.py, answer_flags.py, lenses.py,
                              narrative_score.py, challenge.py, awareness/entity_confusion
        │  gaps (with gap_key, gap_source, severity, difficulty, num_negatives)
        ▼
content strategy (LLM)        content_strategist.py  → plan(): campaigns/pieces, cadence, mix
        │  research-grounded: content_research.py (research_block injected into the prompt)
        ▼
work orders / strategy view   strategy_generator.py  build_work_orders(), strategy_view(),
                              _emit_typed_program(), local program, rich-media binding
        │  identity flows via gap_specifics (campaign_id, content_type, gap_key)
        ▼
plan → tasks materialization  tracking.py  sync_plan(), create_work_order()
        ▼
generation (LLM)              content_generator.py  generate_for_wo(), _gen_prompt(), _outline(),
                              _compliance_autofix(), atomize_draft(); content_batch.py
                              generate_batch()/generate_cluster(); rich_media_generator.py,
                              visual_content.py, heygen_video.py
        │  grounding: authoritative_sources.py, grounding_coverage.py, grounding_retrieval.py,
        │             source_material.py, content_research.py all feed the prompt
        ▼
scoring                       content_quality.py  on_page_score(SEO), aeo_score, geo_score,
                              video_score, serp_grade, structure/readability/slop/citation_ready,
                              analyze_draft() (combines them)
        ▼
measurement / closed loop     content_impact.py  measure_batch(), gap_completion (api/routers/content.py),
                              recent_signals(); feeds back into the NEXT content_strategist plan
```

## WHAT TO AUDIT — dimensions (be exhaustive within each)

### A. Software correctness & robustness
- Bugs, logic errors, off-by-one, wrong operator, inverted condition, wrong default.
- **Silent failures / fail-open:** bare `except:`/`except Exception: pass`, swallowed errors, `.get()`
  chains that mask missing data, LLM calls whose empty/garbage output is treated as success, functions
  that return `[]`/`{}`/`None` on error so the caller proceeds as if it succeeded.
- **Data drops:** a computed value that never reaches persistence or the next stage; rows written with
  a key that nothing joins on; a list truncated (`[:N]`, `LIMIT`, top-N) with no log of what was
  dropped; an LLM response parsed such that items silently disappear.
- **Data drift / identity-join integrity (historically the root disease here):** does every production
  path attach a `batch_id`/`gap_key`/`campaign_id` that is actually **joinable back to the gap it
  serves**? Trace `gap_key` from `gap_model` → `content_strategist` → `strategy_generator` → `tracking`
  → `content_batch`/`content_generator` → `content_impact.gap_completion`. Any place two stages use a
  different key shape for the same entity is a drift bug (pieces earn no gap-closure credit, or the
  wrong gap gets credited).
- Unhandled exceptions on the hot path (job runner / worker); `NameError`/`AttributeError` from a
  clobbered or shadowed def (this codebase has been bitten by this — a subagent redefining a hot-path
  function). Prefer running `run_job()` / the job entrypoint end-to-end over import-only checks.
- SQL correctness: NULL handling, `FILTER (WHERE …)`, division-by-zero in averages, `GROUP BY`
  mismatches, missing `COALESCE`, timezone/`now()` assumptions, and **migration drift** (a column read
  in code that no migration creates, or vice-versa; `ALTER … IF NOT EXISTS` dormant-safe patterns).
- Concurrency / idempotency: can a job double-produce, double-charge, or double-count if retried or run
  by two workers? Are `content_batches`/work-order state transitions idempotent?
- Type/None safety in Python; number formatting; unbounded token/prompt growth (there is history of a
  gap-model 352k-token overflow + a truncation that silently no-op'd a rewrite).

### B. Process integrity — "are the things that should be fixed actually fixed?"
Independently re-verify each **fix-claim** in the CLAIMS TO RE-VERIFY section below. For each, find the
code, confirm it does what's claimed, and try to break it. Two systemic "diseases" were supposedly
eradicated — **re-hunt for both across the whole pipeline, not just where they were found before:**
- **"Measure-then-act-blindly":** any place a signal is computed and then **discarded at the decision
  point** — e.g. a difficulty/severity/quality/lift number is calculated but the count, type, cadence,
  or keep/adjust decision ignores it and uses a constant instead. List every decision point and name
  the signal that drives it; a decision driven by a hardcoded constant when a computed signal exists is
  a finding.
- **"Plan-vs-batch divergence":** any two code paths that produce **different results for the same
  gap/purpose** — the plan/strategy path vs. the batch/on-demand path emitting different content types,
  counts, sizing, keyword sets, or measurement windows for the same gap. They should share one helper.

### C. Is the strategy DYNAMIC and data/goal/research-driven? (core owner concern)
- **Strategy generation is dynamic:** confirm `content_strategist.plan()` actually consumes the gap
  model, business profile/goals, measured signals, and research — not a static template. Feed it two
  very different gap profiles (mentally or in a repro) and confirm the plan changes accordingly.
- **Amount of content is decided from data:** confirm counts (blogs, spokes, videos, podcast
  appearances, social posts, backlinks, refresh cadence, crowd-out pages) come from the gap
  severity/difficulty/`num_negatives` + research helpers in `content_research.py`
  (`cluster_count_for`, `video_count_for`, `podcast_appearance_target`, `social_count_for`,
  `social_atoms_per_piece`, `backlink_target_for`, `publishing_cadence_for`, `refresh_interval_for`,
  `displacement_pages_for`) — **not** capped at "check the box" constants. Specifically probe: does a
  MORE competitive keyword / MORE negative gap yield MORE content? Is any `limit=3`/`[:3]` still capping
  a program below the research target (topical authority wants a pillar + ~8–12 clusters, ~24 strong)?
- **Type mix is research/goal/gap-driven:** confirm the *choice of content types* (article vs. FAQ vs.
  local page vs. video vs. podcast vs. social vs. comparison) is derived from intent/goal/gap_source +
  cited research, and that the SAME type set is emitted on both the plan and batch paths
  (`_emit_typed_program`, tenant `default_content_types` via `industry_profiles.for_business`). Is every
  amount/type decision traceable to a **cited `content_research.py` entry** (has `source`+`url`+`as_of`)?
  Any decision still tracing to an uncited magic number is a finding.
- **Research actually influences decisions, not just prose:** confirm `research_block` changes the
  AMOUNT/TYPE the engine plans (via the count helpers), not merely the prompt text the LLM sees.

### D. Content quality & scoring correctness (does a high score = real goal progress?)
- **AEO/SEO/GEO scoring is correct:** read `content_quality.aeo_score`, `on_page_score` (SEO),
  `geo_score`, `_geo_signal_score`, `video_score`, `serp_grade`, `analyze_draft`. Verify each sub-score
  measures what it claims (e.g. GEO rewards quotations/statistics/citations/fluency per the Princeton
  GEO findings; AEO rewards direct-answer/answer-para/entity clarity; SEO rewards on-page structure,
  headings, keyword coverage without stuffing). Check thresholds/weights for arbitrariness, gaming, and
  **false confidence** (a piece that scores 90 but wouldn't rank/citation-win). Confirm scores are
  computed on the **final** published body (not a pre-revision draft) and are actually persisted &
  surfaced (no silently-discarded grade — there is history of grading being dropped).
- **Quality of generation:** confirm source material + the authoritative-sources grounding + the
  research KB + the per-piece gap/keyword signals actually **reach the generation prompt**
  (`content_generator._gen_prompt`, `_outline`), and that ungrounded generation **fails loud** rather
  than producing confident-but-unsourced text. Confirm word-count/length targets come from research and
  drive real draft length (no long-form that silently truncates; caps track `serp_target_words`).
- **Reputation & regulatory safety (this tenant is financial services / life insurance):** confirm the
  business's NAP / contact facts come only from a **trusted record**, never leaking a competitor's
  number (`content_generator._verified_nap`). Confirm compliance rewriting (`_compliance_autofix`) does a
  **focused/surgical** rewrite of the offending text (not a full-body rewrite that loses content), has
  **content-type-dependent** token caps (higher for white papers/deep articles), and **rejects** a
  rewrite that clipped the body below a sane fraction. Look for any path that could publish a
  non-compliant claim (guarantees, unlicensed advice) or defamatory statement about a competitor.
- **Closed loop:** confirm `content_impact.measure_batch`/`gap_completion`/`recent_signals` measure
  real SoV/goal-alignment/rank deltas and that those measured deltas **feed back into the next plan**
  (`content_strategist` reads recent signals/quality to make more of what works for THIS tenant).
  Confirm the AI-Visibility / goal_alignment score uses the canonical wrong-entity exclusion everywhere
  (`answer_flags.NOT_WRONG_ENTITY_SQL`) so a name-colliding competitor's answers don't dilute the score.

### E. Additional dimensions (added for completeness — audit these too)
- **Defensibility of the AI-Visibility score:** is the headline 0–100 score reproducible, explainable,
  and robust to noise (engine flakiness, one bad prompt, entity confusion)? Could a customer or
  competitor plausibly dispute it? Trace exactly how it's computed and aggregated across engines/prompts.
- **Multi-tenant isolation & authz:** every query and endpoint scoped by `business_id`/org; no cross-
  tenant leakage; owner/operator/super-admin boundaries enforced; billing master switch respected.
- **Business-agnostic generalization:** run the reasoning for a **non-finance** tenant — do industry
  source packs, profiles, keyword logic, and compliance still behave, or is finance hardcoded anywhere?
- **Cost / budget integrity:** is every LLM/provider call cost-recorded? Known risk: unrecorded LLM cost
  → budget-cap leak. Can a run exceed the visible/editable budget cap? Are paid data jobs (DataForSEO,
  PageSpeed, etc.) gated and scheduled sanely (history: paid jobs never auto-scheduled; DataForSEO
  40104-unverified)?
- **Security:** OWASP Top 10 pass on the API — injection (SQL/prompt), secrets in code/logs, SSRF in
  site-crawl/URL-ingest, auth on every mutating route, PII/GDPR handling, webhook signature verification
  (HeyGen/Stripe), safe handling of third-party publish tokens (connections vault).
- **Prompt-injection & grounding integrity:** crawled site content and source material flow into prompts
  — can a malicious source string steer generation or exfiltrate? Is retrieved grounding trusted blindly?
- **Observability:** are failures visible (logged/surfaced) or swallowed? Would an operator know if a
  job half-failed, a batch produced 0 pieces, or a score was never written?
- **Test/eval honesty:** do the tests actually assert behavior, or are key paths mocked to always pass?
  Is there coverage for the scoring math, the count helpers, the identity joins, and the closed loop?
  Flag any test that would pass even if the feature were broken.
- **FE/BE contract drift:** hardcoded mirrors on the console (e.g. content-capability caps) that can
  drift from the backend; the produce-next vs. To-Produce sources agreeing; `has_draft`/status filters.

## CLAIMS TO RE-VERIFY (do not trust — check each, report holds / does-not-hold)
1. Both systemic diseases eradicated: **no measure-then-act-blindly** and **no plan-vs-batch divergence**
   anywhere in the pipeline.
2. Plan & batch share sizing via `content_batch.difficulty_to_target` + `local_spoke_target` +
   `_local_spokes`; the old `_local_keywords(limit=3)`/`[:3]` cap is gone / fully dynamic by
   competitiveness.
3. `generate_batch` and `ensure_impact_batch` baseline/measure over the **identical** prompt window for a
   shared `gap_key` (both route through `_prompts_for_gap`, `prematched=` target_prompts).
4. The wrong-entity exclusion `NOT COALESCE(entity_confusion,false)` is on **every** `AVG(goal_alignment)`
   aggregation codebase-wide (report_generator, audits, run_metrics, ai_state_audit, content_batch,
   strategy_advisor, public_report, timeline_estimator, impact_report, tracking, feedback_loop,
   notifications, lenses, challenge).
5. All 8 `content_research` count helpers are wired into real plan decisions (not just defined).
6. Rich-media/video/image/quote-card production is gap-linked (`_gap_link_for_wo`) and joins the impact
   loop; `measure_all` includes `'generating'` batches so mainline baselines get measured.
7. SERP/GSC **rank measurement** is wired (dormant until GSC connected) and non-text **mix** is
   research-grounded via `content_research.py` (48 cited entries).
8. NAP is trusted-record-only; compliance autofix is surgical + content-type-dependent cap + reject-if-
   clipped; strategist puts the word limit in the outline so long-form plans to fit.
9. Content `content_type` flows all the way into generation (template selection), not just labels.
10. Known open items still open (confirm, don't fix): no SMTP email; paid data jobs not auto-scheduled;
    DataForSEO unverified; several rank/data features dormant pending owner keys.

## METHOD
1. Read this brief + `reputation_engine/CONTENT_PIPELINE_REVIEW_BRIEF.md` if present. Build the mental
   model of the loop above.
2. **Trace, don't skim.** Follow 3–4 representative journeys end to end: (a) a competitor/comparison gap
   → plan → generation → score → measurement; (b) a local-SEO gap → local program; (c) a negative-
   narrative gap → crowd-out/displacement plan; (d) a rich-media/video piece. At each hop check identity
   join, dynamic sizing, dynamic type, grounding-into-prompt, scoring, and measurement credit.
3. Adversarially verify each candidate finding (repro/trace) before writing it. Discard the ones you
   can't substantiate.
4. Reason from the domain for coverage gaps (what a reputation engine obviously should handle that this
   doesn't), and report them.

## OUTPUT
- **Executive summary** (5–10 lines): is it production-ready? Biggest risks. Does the engine reason
  soundly (dynamic strategy, research-driven amounts/types, correct scoring, real goal impact)?
- **Claims re-verified** table: each claim above → holds / partially / does-not-hold + evidence.
- **Findings**, most-severe first, each with: severity, `CONFIRMED`/`PLAUSIBLE`, `path:line`, concrete
  failure scenario, and a concrete fix.
- **Domain/coverage gaps** the code doesn't handle.
- **Verdict:** ship / ship-with-fixes / not-ready, and the shortest list of blockers.
```
