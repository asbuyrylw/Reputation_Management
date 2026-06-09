# Reputation Crowding-Out Engine — Roadmap & To-Do

A living checklist. Check items off as completed. Sections are ordered roughly by
priority within each group. Status keys: `[ ]` todo · `[~]` in progress · `[x]` done.

---

## 0. Already built & tested (done)

- [x] Module 1 — AI-state audit + monitoring harness (prompt battery, scoring, gap model, diff)
- [x] Module 2 — Strategy + work-order generator (phased plan, auto/semi/manual, tool registry)
- [x] Module 3 — Technical site-crawl audit (regex + selectolax, robots.txt, Lighthouse-optional)
- [x] Module 4 — Client report generator v2 (exec summary, trend charts, before/after answers, attribution)
- [x] Module 5 — Execution tracking + attribution (work-order lifecycle, asset logging, alerts)
- [x] cost.py — per-call cost ledger + monthly budget caps
- [x] http.py — resilient HTTP (retry/backoff, failure-vs-empty distinction)
- [x] Orchestrator — full `run` + monthly `cycle`
- [x] Multi-sample auditing (averages out LLM noise)
- [x] Structured-output JSON modes for the orchestrator LLM
- [x] Per-business config (samples, budget, alert threshold, disabled tools)
- [x] Tested end-to-end against a real Postgres instance

---

## 1. Core capability gaps (highest impact — build next)

- [x] **Module 6 — AI content generator (the missing gap-filler).** Turns each
      generatable content work order into a finished DRAFT (FAQ, schema JSON-LD,
      article, bio, GBP post, review-request). AI generates, human approves, system
      tracks. Tested against live Postgres (5 tests).
  - [ ] Pull from pgvector memory first (hook in place; no-op until pgvector wired)
  - [x] Win-Gate-style self-evaluation rubric + bounded auto-revision before queueing
  - [x] Compliance pre-screen (no performance promises, broker-dealer disclosure, etc.)
        as a first-class step; fails safe (NULL = human must review) if screener unavailable
  - [x] Write outputs as `pending_review` assets; approval promotes to `assets` +
        advances the work order. Never auto-publishes.
- [ ] **Human-review queue** — interface/workflow for approve → publish → log
      (one-click). CLI approve/reject exists; a dashboard view would live in FireGEO.
- [x] **Module 7 — timeline estimator.** Range-based projection (optimistic/expected/
      conservative) for time-to-dominance, from entrenchment + plan throughput +
      observed velocity. Explicit confidence (low→high as audits accumulate); always a
      projection, never a promise; drown-out framing. Wired into monthly cycle + report.
      Tested against live Postgres (5 tests).
- [x] **Module 8 — acceleration advisor.** Models how specific quantities of
      third-party/human levers (articles, earned links, videos, press, genuine
      reviews, podcasts) compress the timeline; ranks levers by impact and bundles
      light/moderate/aggressive scenarios with a realism cap. Range-based, never a
      promise; genuineness guardrails on reviews/placements. Wired into cycle +
      report. Tested against live Postgres (4 tests).
- [x] **Module 9 — outcome feedback loop.** Learns per-business how much each lever
      type actually moved goal_alignment across run-windows; writes learned
      effectiveness + baseline that recalibrate the estimator and advisor away from
      generic defaults. Confidence rises with sample size; correlation not proof.
      Wired into the cycle (learn step before estimate/advise). Tested (5 tests).
- [x] **Idempotent, resumable orchestrator runs** — `runstate.py` checkpoints each
      step; a failed/interrupted `run`/`cycle` resumes with `--resume`, skipping
      completed steps so a mid-run failure never re-spends the audit budget. Failed
      steps record their error. Tested against live Postgres (4 tests).

## 2. Quality foundation (do early — everything rests on it)

- [x] **pytest suite** — unit tests for scoring/diff/attribution math + failure-vs-empty
      logic; integration tests against a throwaway Postgres (19 tests passing)
- [x] **CI** — GitHub Actions running ruff + mypy + tests on every push (.github/workflows/ci.yml)
- [ ] **Alembic migrations** — replace raw schema.sql + scattered ALTERs (you already
      use Alembic on NexScholarship)
- [x] **Pydantic config validation** — `config.py` validates every env var at
      startup (typed, range-checked, DSN shape, orchestrator/key coherence) and
      surfaces one clear error instead of a cryptic mid-run failure. Wired as
      step 0 of preflight. Tested (9 tests).
- [x] **Structured logging + per-run correlation IDs** — `logging_setup.py` tags
      every log line with business_id + run_id (bound automatically by runstate);
      optional JSON mode (REP_LOG_JSON=1) for log tooling. Tested (2 tests).

## 3. Open-source integrations — the set that matters

- [x] **python-seo-analyzer integration** — integrated as a parser-layer enrichment
      (keyword extraction + richer SEO warnings) run on HTML fetched by our own
      resilient http layer, NOT pyseo's fragile networking. Keeps Firecrawl-ready.
      Falls back cleanly if not installed. (Design note: a parser-layer integration
      proved better than a wholesale crawler swap — pyseo's urllib3 layer fails on
      some hosts; ours doesn't.)
- [x] **OpenCite metrics (Module 10 — citation analytics)** — citation momentum
      (first/last-seen, frequency, rising/falling/new/dropped), share of voice by
      owned/neutral/contested, and persona/location lenses (audit now probes a local
      lens so you can show "what someone in your market sees" vs. generic). Wired into
      cycle + report. Tested against live Postgres (5 tests + lensed-battery unit test).
      *(This was the most differentiating feature — the share-of-voice gap, closed.)*
- [ ] **pgvector** — enable in existing Postgres for citation/content semantic memory
      + dedup. *(No new infrastructure.)*
- [x] **Firecrawl JS-render fetch** — crawler re-fetches fully-rendered HTML via
      Firecrawl when a page looks client-side-rendered (auto mode = only when thin,
      saving credits), then re-extracts. Fixes the SPA/JS blind spot before paid runs.
      Info marker excluded from defect counts. Tested (4 tests).
- [ ] **FireGEO shell** — open-source SaaS layer (auth, Stripe billing, Next.js
      dashboard) wrapped around the Python engine. *(Last; only once engine is proven.)*

## 4. Open-source — reference / consider (don't adopt wholesale)

- [ ] Mine `github/awesome-copilot` search-AI-optimization agent prompts for the orchestrator
- [ ] Crib prompt patterns from OPC skills GEO example + `claude-seo` repos
- [ ] Register `openshorts` as a free `video_creation` option in the tool registry
- [ ] Borrow camoufox's geolocation/locale-spoofing idea ONLY (not its anti-detect stack);
      prefer plain Playwright for JS rendering
- [ ] Park `clean-mcp` — for later "expose engine as an MCP tool" direction
- [ ] Bookmark `amplifying-ai/awesome-generative-engine-optimization` as a map of the space

## 5. The precondition gate (needed before any paying client)

- [x] **Preflight + runbook prepared.** `rep_engine/preflight.py` validates DB, keys,
      per-engine live request/response shapes, and orchestrator JSON with minimal spend
      before any full audit. Step-by-step setup guide: First_Live_Run_Checklist.docx.
- [ ] **First live end-to-end run** against a real domain with real API keys (Team
      Unstoppable). Run preflight first; fix whatever it surfaces; then `orchestrator run`.
  - [ ] Set REP_DB_DSN + load schema.sql..schema_v5.sql on production Postgres
  - [ ] Set orchestrator + answer-engine keys; update model IDs + cost.py pricing
  - [ ] Verify Perplexity model name (PH 9) — preflight probe will flag
  - [ ] Verify OpenAI Responses + web_search request shape (PH 10) — preflight probe
  - [ ] Verify Anthropic web_search block (PH 11) — optional grounding
  - [ ] Verify Gemini search-grounding shape (PH 12) — preflight probe
  - [ ] Review the report; only then use --generate-drafts; approve content by hand

---

- [x] **Tiered model routing + adaptive sampling** — high-volume scoring runs on a
      cheap model tier (Haiku / 4o-mini) while synthesis uses the full model; sampling
      stops early when scores are stable and clear of the decision boundary (≈50%% fewer
      scoring calls in tests). Cost ledger tracks both answer + score ops; cheap-tier
      pricing added. Tested (6 tests). *(Tiered model routing + adaptive sampling done.)*

- [x] **Competitor share-of-voice benchmarking (Module 11)** — register competitors,
      run the same battery, compare appearance rate across category questions; report
      shows your rank + the biggest gap (questions a rival wins that you don't). Reuses
      citation machinery; failed calls excluded; transparent mention heuristic. Tested (7).

## 6. AI Visibility service — go-to-market & packaging

- [ ] Finalize the $20K/yr offering using the AI_Visibility_Service.docx as the spec
- [ ] Define 2–3 pilot success metrics before any client starts
- [ ] First pilot: run engine against Team Unstoppable (real domain, real keys)
- [ ] Build the monthly-report → client delivery rhythm
- [ ] Lead pitch with the crowding-out reframe (NOT "make the MLM label disappear")

## 7. Local lead-gen sites (separate but related deliverable)

- [ ] Confirm DBA/brand names + required disclosures with Primerica compliance BEFORE launch
- [ ] Stand up ONE flagship site done well (don't launch a thin network → doorway-page risk)
- [ ] Service pages + 4–6 local landing pages, fully written (no stubs)
- [ ] Google Business Profile claimed/optimized + review generation via GHL
- [ ] Lead capture → GHL with source attribution → AI appointment-setter
- [ ] Run 60–90 days, measure booked appointments per page/keyword, then template

---

## 8. Voter-roll lead pipeline (the other build)

- [ ] Fill placeholders in lead_pipeline.py (DB, AI caller, GHL, enrichment, income-by-ZIP)
- [ ] Fill placeholders in geo_score.py (Census key, ACS year, persistent-poverty CSV)
- [ ] Wire resolve.py to the existing nonprofit waterfall (person mode)
- [ ] TCPA/DNC compliance: DNC scrubbing + state calling-window enforcement BEFORE going live
- [ ] Verify the compounding-pitch numbers (use conservative ~7% real alongside 10% nominal)
- [ ] Build the AI-caller result webhook receiver (closes the appointment-booking loop)

## 9. Primerica nonprofit-data plays (from the call)

- [ ] Add dual-axis partnership-fit scoring to primerica_prospects.py (NTEE × revenue band)
- [ ] Start niche: veteran-serving human-services orgs, $500K–$3M revenue, OH/KY/IN
- [ ] Worksite-marketing list (nonprofit employers by size/geo)
- [ ] Officer-prospect list (comp-segmented from 990 Part VII)
- [ ] Community-connector / recruit list (distressed-area, mission-aligned orgs)
- [ ] Co-marketing: financial-literacy workshops through aligned nonprofits

## 10. NexGrant demo for his nonprofits (warm follow-up)

- [ ] Gather current legal names, EINs, one-line mission for each active entity
- [ ] Confirm status of Pleasant Vineyard / Wilderness Ridge (the "retreat center — sold" note)
- [ ] Run EINs through NexGrant live; surface foundation + Ohio opportunities a federal search misses
- [ ] Scholarship-as-part-of-FNA pilot: offer NexScholarship free to Primerica families w/ high-schoolers

## 11. Cross-business data plays — feeding Team Unstoppable (from the call)

The strategic idea: NexGrant and NexScholarship are sitting on data + reach that can
become a top-of-funnel and warm-intro engine for the Primerica Team Unstoppable
financial-services business. Keep each product's data use compliant with its own
terms; this is about routing *people Logan already has a relationship with* toward an
FNA conversation, not scraping/reselling.

- [ ] **NexGrant nonprofit DB → Primerica prospecting.** Use the 1.8M nonprofit /
      400K-foundation enrichment to build worksite-marketing + officer-prospect lists
      (this overlaps Section 9 — keep them linked). Niche-first: veteran-serving
      human-services orgs, $500K–$3M revenue, OH/KY/IN.
- [ ] **NexScholarship → FNA funnel.** Offer scholarship matching free to families
      with high-schoolers; the scholarship/college-cost conversation is a natural,
      non-salesy on-ramp to a financial-needs analysis. Tie into Section 10's pilot.
- [ ] **Nonprofit officers/employees → financial-literacy workshops.** Co-marketing
      through aligned nonprofits (Section 9) as warm intros, not cold outreach.
- [ ] **Shared contact/automation rail.** Route all of the above through GHL with
      clear source attribution so Team Unstoppable can measure which channel (grant
      client, scholarship family, nonprofit workshop) actually books FNAs.
- [ ] **Reputation engine as the trust layer.** Once Team Unstoppable's AI-visibility
      is solid (this engine), it backstops every warm intro above — when a prospect
      googles/asks AI about the team, the accurate narrative is what they find.
- [ ] **Guardrails:** keep NexGrant/NexScholarship data usage within each platform's
      terms and privacy commitments; financial-services outreach stays compliant
      (broker-dealer disclosure); never present scholarship help as contingent on an
      FNA. Genuine value first.

---

## 12. Outreach Engine — second product (lead enrichment + compliance-gated dispatch)

A standalone product (separate DB + separate GHL) for the Primerica financial-services
side. Ingests voter rolls (individuals) + nonprofit DB (orgs/officers) → unified
contacts → enrich → segment by type/age/income/geo into intent (financial_product /
recruit / co_marketing) → compliance gate → dispatch via Dialora calls / email /
FB+LinkedIn → separate GHL CRM.

- [x] **Built end-to-end (v0.1):** ingest, enrich (waterfall + local fallback),
      segment (intent + channel plan + priority), compliance (call hard-gate; email/
      social light-gate), dispatch (Dialora + GHL adapters with real endpoint shapes),
      pipeline orchestrator. 9 tests passing incl. the call-gate blocking tests.
- [ ] **Before live calling (REQUIRED):** wire a real DNC scrub service
      (OUTREACH_DNC_API); confirm + populate state voter-use rules with counsel
      (VOTER_COMMERCIAL_ALLOWED); never set call consent without documented written consent.
- [ ] Set Dialora agent webhooks (financial + recruiting agents) + API key
- [ ] Set the SEPARATE GHL instance creds (not NexGrant's)
- [ ] Point enrichment at the real waterfall (OUTREACH_WATERFALL_BASE/KEY)
- [ ] Optional: ACS income-by-zip CSV for better income banding
- [ ] Build the Dialora result/CDR webhook receiver (close the loop: call → outcome → GHL)
- [ ] Real send for email/social (currently queued to GHL; wire GHL campaigns/workflows)
- [ ] Ties to Section 11: this IS the engine that operationalizes the cross-business
      plays (voter + nonprofit data → financial-services outreach).

## 13. Outreach Engine — quality / cost / trust enhancements (prioritized backlog)

Ordered by real-world value. The meta-point: this product's ceiling is set by whether
the compliance + feedback loops are real, not by feature count. Build the not-optional
tier first.

**Tier 1 — not optional for a live calling system**
- [ ] **Dialora result/CDR webhook receiver** — ingest call outcomes (answered,
      voicemail, booked, not-interested, callback, DNC-requested). Turns one-way
      blasting into a system that learns. Highest-value single addition.
- [ ] **Global DNC-on-request handling** — when someone says "don't call me again"
      on a call, flow it straight into compliance as a permanent block. Compliance-critical.
- [ ] **Suppression / global do-not-contact list** — converted, complained, opted-out,
      or existing clients are excluded at dispatch. Prevents wasted spend + pestering.
- [ ] **Idempotent, resumable, rate-limited dispatch** — checkpoint sent actions;
      configurable calls-per-hour cap; no double-dial within N days. Quality + cost control.

**Tier 2 — port from the reputation engine (near-free, immediate value)**
- [ ] **Cost ledger + monthly budget caps** — per-action cost (call minutes, enrichment),
      cost-per-contact + cost-per-booking, stop at budget. Copy-adapt from reputation cost.py.
- [ ] **Preflight check before live runs** — verify DNC service, GHL creds, Dialora
      webhooks, and the voter-use table are wired before any live dispatch.

**Tier 3 — quality / conversion compounders**
- [ ] **AI-personalized call scripts + message copy per segment** (intent x product x
      persona), human-approved via the content-generator + compliance-gate pattern.
- [ ] **Outcome-based feedback loop** — learn which segments actually convert for THIS
      business; recalibrate segmentation from real booking rates. Lowers cost-per-acquisition.
- [ ] **A/B testing on scripts + channels** — randomize variants, let outcome data pick winners.

**Tier 4 — direct per-contact cost reduction**
- [ ] **Phone/email validation before dispatch** — line-type/deliverability check so you
      don't spend a call credit on a dead number or burn sender reputation on a bounce.
- [ ] **Tiered enrichment (stop-when-reachable)** — enforce cheapest-source-first, stop
      as soon as a usable phone/email is found; don't pay for enrichment you don't need.
- [ ] **Channel-cost-aware routing** — lead with ~free email/social for low-priority/low-band
      contacts; reserve paid Dialora calls for highest-value prospects who engage.

**Tier 5 — operability / trust (table-stakes to operate + sell)**
- [ ] **Structured logging + audit trail** — defensible record of who was contacted,
      when, on what basis, with what consent (capture the compliance decision at dispatch time).
- [ ] **Dashboard** — funnel view (ingested → enriched → eligible → dispatched → answered
      → booked) by segment + channel. Can't optimize what you can't see.

## 14. Semantic-depth analyzer (Module 12) — DONE

- [x] **Semantic-depth page analysis** — scores each crawled page on the on-page
      signals 2026 GEO research links to AI citation: entity/topic coverage,
      title-to-query alignment, front-loading (first 30%), freshness, lexical
      breadth, question coverage. Produces a 0-100 citation-readiness score +
      actionable recs. Backlinks/schema deliberately EXCLUDED from the score
      (controlled studies found they don't move AI citations). Wired into the
      crawler; missing entities feed the gap model as content opportunities.
      Tested (8 tests). Research basis: earned-media dominance, first-30%% citation
      bias, ~2x freshness lift, fan-out/entity coverage > single-keyword density.

## 15. Mention monitoring + reply drafting (Module 13) — DONE

- [x] **Unlimited mention monitoring + reply drafting** — the BizReply-style
      capability with NO per-business license cap (monitor as many businesses /
      keywords as your own infra allows). Pluggable SOURCE adapters (built-in:
      Reddit public search, Google News RSS; register your own). Dedups, scores
      relevance + sentiment, supports negative keywords. Drafts on-brand replies
      via the existing content-generator LLM + compliance gate. **Never auto-posts**
      — every reply is pending_review; human approves before posting. Compliance
      fails safe (screener unavailable => human must review). Crowding-out spirit:
      replies are helpful/non-defensive, never disparaging. Tested (7 tests incl.
      the never-auto-post guarantee + unlimited businesses/keywords).
- [ ] Optional later: add more source adapters (X/Twitter, LinkedIn, review sites)
      as APIs/keys allow; a simple review-queue UI for approvals; auto-post via
      platform APIs ONLY behind an explicit per-business opt-in + compliance sign-off.

---

## 16. Code-review fix backlog (added 2026-06-09)

From a multi-agent review of the **Reputation Engine + Outreach Engine + waterfall
enrichment**, with every concrete claim verified against source. Grouped by area,
ordered by priority within each group. File:line refs are as of the review date.
Meta-point: ZERO live clients yet (`output/` holds only `.gitkeep`). Fix the
client-facing-number bugs + the live-API adapters, freeze the Outreach Engine behind
counsel review, and run ONE real audit before building anything new.

> **Implementation pass — 2026-06-09.** Items checked `[x]` below were fixed +
> compile-checked this session (regression tests added where pure-logic: 3 reputation
> www-strip tests + 2 DB-gated KPI/ingest tests + 8 waterfall-matching tests + outreach
> age tests, all green locally). The TCPA calling-window gate (16.2) and dial-time
> DNC/window re-checks were found ALREADY IMPLEMENTED in the engine's own newer code
> (`callwindow.py` + `compliance.dnc_recheck`) — marked done, not re-done. NOTE: the
> Outreach Engine files are syncing via Google Drive and changing under edit; deeper
> outreach changes were deferred to avoid clobbering concurrent work.

### 16.1 Verified correctness bugs — Reputation Engine (fix first; trivial, in-repo)

- [x] **Failed rows dilute the two headline KPIs.** `contested_rate`/`owned_rate`
      aggregation omits the failed-row filter in `diff()`, `tracking._run_metrics`, and
      `report_generator._run_series`, so `AVG(CASE WHEN contested…)` counts every
      failed/empty call as a real 0 — diluting the numbers in every client report,
      attribution row, and spike alert. Add `AND NOT COALESCE(failed,false)`
      (ai_state_audit.py:715, tracking.py:153, report_generator.py:59). Add a regression test.
- [x] **`lstrip('www.')` mangles domains** — `www.weather.com` → `eather.com`; corrupts
      owned/contested classification + share-of-voice for any domain whose char after the
      prefix is in {w,.}. Replace with `d[4:] if d.startswith('www.') else d`
      (citation_analytics.py:72,80; competitor._mentions). Add a regression test.
- [x] **Voter-ingest insert count inflated** — counts `ON CONFLICT DO NOTHING` skips as
      inserts (ingest.py:80). Mirror the nonprofit path: `RETURNING id`, `inserted += 1`
      only on a returned row.
- [ ] **Budget cap not enforced on full-model calls.** `build_gap_model` and every
      `content_generator` LLM call bypass the budget guard AND never record cost —
      invisible to the ledger. Wrap them in the same pre-call check + cost log.
- [ ] **Adaptive sampling is inert at default** `samples_per_prompt=2` (can never save a
      call) and can lock in a wrong-but-confident mean on a 2-point spread when enabled.
      Require ≥3 samples before early-stop; widen the decision-boundary guard.
- [ ] Minor: greedy `{.*}` JSON extraction fails on trailing prose with braces;
      `site_crawl` uses `Optional` without importing it; exact-280-char ellipsis is misleading.

### 16.2 Compliance holes — Outreach Engine (HIGHEST STAKES; freeze live call/email until fixed + counsel)

- [x] **TCPA calling-window gate is hardcoded `window_ok = True`** *(done in engine's own newer code: `callwindow.py` + opt-in `OUTREACH_ENFORCE_CALL_WINDOW`, fail-safe on unresolved zone, dispatch re-checks at dial time)* (compliance.py:91) — no
      tz logic; README/docstring falsely claim hours are enforced. Implement a tz-aware
      8am–9pm-local check from state/ZIP, default BLOCKED when tz unknown, AND re-evaluate
      at dial time inside dispatch (like suppression). Add to preflight. ($500–$1,500/call.)
- [ ] **Email channel has no CAN-SPAM machinery** — no unsubscribe link / `List-Unsubscribe`
      header, no physical postal address; `_email_optout` is a dead read. Inject all three
      into every email body, refuse to queue templates lacking them, and add an inbound
      opt-out handler that calls `suppression.suppress('email',…)`.
- [ ] **Email/social "sends" never actually send** (dispatch.py:393–424) yet are ledgered,
      logged "queued," and counted as `emails_dispatched`. Either wire the real GHL
      send/campaign call (set `sent` only on 2xx) or rename `*_dispatched` → `*_synced_to_ghl`
      and gate `billable=True` behind a confirmed send.
- [ ] **A DNC request can be permanently dropped.** Webhook DNC routing commits
      `processed=FALSE` then runs `dnc_request` separately; on redelivery the dedup
      early-return skips suppression. Make DNC-request routing idempotent + re-driven on
      redelivery (or run it in the same transaction that marks the event processed).
- [ ] **Consent is a bare overwritable boolean** with no timestamp/text/version/proof,
      written outside the append-only `audit_log`. Make it an evidentiary record
      (when / what-text / version / proof-ref) in `audit_log` — can't substantiate a TCPA
      prior-express-written-consent defense otherwise.
- [x] **DNC/consent frozen at screen time, never re-checked at dial time** *(dial-time DNC re-scrub `compliance.dnc_recheck` + dispatch window re-check now present; consent-freshness expiry still open)* (federal DNC
      requires re-scrub every 31 days). Re-verify DNC + consent freshness at dial time;
      expire screens older than 31 days.
- [ ] **Broker-dealer / financial-promotion disclosure is only LLM-prompt-encouraged**,
      never structurally required/injected, and a call can fire with `script=None`
      (agent's own unreviewed script). Require an approved script + injected disclosure
      before any financial call can dispatch.
- [ ] Voter-use clearances live in a hand-edited code constant with no reviewer/date/source
      provenance — move to a DB table with provenance. GHL upsert exports income-band PII
      before eligibility checks — gate the export behind eligibility.

### 16.3 Architecture / infrastructure debt

- [ ] **Single `db.py` through config + pooling.** DSN + `db()` factory is copy-pasted in
      all 15 reputation modules and bypasses the Pydantic placeholder-DSN validation.
      Extract `rep_engine/db.py` exposing `get_dsn()` from `config.settings().rep_db_dsn`,
      backed by `psycopg_pool.ConnectionPool`.
- [ ] **Outreach connection churn.** `evaluate_contact` opens 3 connections/contact via
      `is_suppressed` (~15k at 5,000 contacts); rate-limiter `sleep()` (up to ~60s) runs
      while holding an open transaction with uncommitted writes. Thread the open conn
      through; commit before sleeping.
- [ ] **Adopt Alembic** (already used on NexScholarship). Convert the 8 numbered `.sql`
      files + in-code `ALTER`s + conftest re-declaration into migrations; have conftest run
      `alembic upgrade head`.
- [ ] **Response-shape fixture tests for the live-API adapters (PH 9–12)** — none today;
      shapes change often. The OpenAI Responses adapter lacks defensive parsing (emits
      garbage on a stale shape instead of a clean failure). Add fixtures; make ruff/mypy
      CI gating (drop `|| true`).
- [ ] **De-duplicate the Anthropic request/parse path** (orchestrator_text /
      `_anthropic_complete` / AnthropicEngine — 3 copies, the area most likely to rot on an
      API change).
- [ ] **Commit answer rows per-engine in `audit()`** so a mid-audit crash leaves
      ledger + answers consistent.

### 16.4 Output polish gaps (client report)

- [ ] **Exec-summary headline rests on the weakest stat** — can assert "improving" off a
      2-point trend with no significance guard, and renders a percentage-POINT delta as a
      percent (`+18%`) a client reads as relative growth. Require ≥3 runs before a
      directional verb; render deltas as percentage-points.
- [x] **Four report sections silently vanish on any exception** (timeline, acceleration,
      share-of-voice, competitor) with no log/stub → inconsistent month-to-month
      deliverables. Change bare `except: pass` (report_generator.py:336,356,378,406) to
      `log.warning` + a "data not available this period" stub.
- [ ] **PDF + branding** — generate a PDF (LibreOffice `--headless`) with cover page, logo,
      page numbers, confidentiality block; stop shipping a raw editable `.docx`.
- [ ] **Metrics table** shows raw 0–1 decimals + the internal term "goal alignment" with no
      client-facing definition while rates elsewhere are percentages. Normalize formatting;
      add a one-line glossary.
- [ ] **BEFORE/AFTER quotes** are verbatim with no defamation/profanity screen + a
      mid-sentence 280-char cut. Add a screen + clean truncation. (Selection is toward
      best-aligned/most-improved prompts — fine.)
- [x] **Outreach dashboard** interpolates labels into HTML without `html.escape()` — latent
      stored-XSS the moment a label carries AI/user text. Escape all interpolated labels.
- [ ] Produce one polished, watermarked SAMPLE PDF as the standing sales leave-behind.

### 16.5 Voter-roll data quality

- [~] **DOB/birth_year alias + age CHECK.** Add `dob`/`birth_year` aliases (derive age) so
      common DOB-only state files don't yield NULL age and silently lose all recruit
      candidates; add `CHECK (age IS NULL OR age BETWEEN 16 AND 110)`.
- [ ] **Ship real ACS median-income-by-ZIP** (free Census). The income-by-ZIP / Census /
      persistent-poverty data the roadmap implies does NOT exist on disk, so `income_band`
      is always None without a paid key and everyone collapses to `term_life`. Stamp it as
      **geo-derived, not personal** (ecological fallacy); add per-field provenance.
- [ ] **Address/name normalization before dedup.** No USPS standardization / whitespace /
      suffix / ZIP+4 handling today, so `1 Main St` vs `1 Main Street`, middle initials,
      `45202` vs `45202-1234` survive as separate humans and cross-source dedup fails. Add
      libpostal/USPS normalization + nickname folding into the dedup hash.
- [x] **Line-type honesty** — local fallback labels every shape-valid number `mobile` from
      digit count. Label `unknown` until a real validation vendor says otherwise.
- [ ] **Capture party / vote-propensity** if the source license permits — the single most
      predictive segmentation signal currently dropped at ingest.
- [ ] Reframe segmentation honestly: it's age-band + ZIP-median geo-segmentation, not
      income/life-stage (ignores children, homeownership, marital status). Source those
      signals or relabel.

### 16.6 Waterfall enrichment quality

- [x] **Token-exact name matching.** `_name_matches_local` (waterfall.py) uses an unanchored
      substring test → verified false positives (`editor@`↔"ed", `benefits@`↔"ben",
      `timothy@`↔wrong "Tim") persisting at high/medium. Replace with token-exact local-part
      matching.
- [x] **Exact registrable-domain matching.** Domain filter uses `in` containment → accepts
      `notacme.org`, `myacme.org`, `acme.org.evil.com`, `chai.org`↔`ai.org`
      (waterfall.py:80,231). Use equality + `endswith('.'+domain)` for true subdomains.
- [ ] **Verify the candidates you actually trust.** Reoon/MailTester runs only on pattern
      guesses, never on the loosely-matched scraped/DDG candidates trusted at `high`. Verify
      scraped/DDG hits before labeling `high`.
- [ ] **One confidence gate across both engines.** `outreach_engine/enrich.py` drops
      confidence/provenance and treats any MX-resolving email as reachable. Carry
      `email_confidence`/`source` through and add `MIN_CONTACT_EMAIL_CONFIDENCE` so the same
      regulated-email decision faces one bar.
- [ ] **Role-account handling** — map Reoon `role_account`/`inbox_full` to `low` for
      per-person rows so `info@`/`sales@`/full mailboxes aren't stamped as an individual's
      verified email.
- [ ] **Phone enrichment is effectively absent** (manual 25-credit path only) yet routing
      ranks `call` highest-EV. Add an automated, DNC/TCPA-aware phone-enrichment stage or
      down-rank `call` until phone coverage is real.
- [ ] Lesser: multi-domain mode returns first-hit not highest-confidence; pattern guess
      always `first.last@` with no firmographic prior; add a negative cache + cross-person dedup.

---

## Notes / decisions log

- Ethical line (firm): crowding-out, never suppression. Enforced in prompts, plan,
  report, and the generation module's compliance gate.
- Cross-business plays (Section 11): warm intros from data Logan already has a
  relationship with — not scraping/reselling; keep within each product's terms;
  value-first, never make scholarship help contingent on a financial conversation.
- Stack: Postgres only. n8n (self-hosted) for connector glue. Provider-agnostic LLM core.
- Sequencing logic: quality foundation + python-seo-analyzer first (cheap, no live-API
  dependency), then Module 6 generation (biggest capability jump), then metrics/memory,
  then the live-API gate, then the SaaS shell.
