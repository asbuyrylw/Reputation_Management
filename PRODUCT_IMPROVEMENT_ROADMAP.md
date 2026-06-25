# Reputation Console — Product / Service / UX Improvement Roadmap

> Produced by a 12-dimension multi-agent audit (2026-06-24): each dimension was mapped
> against the actual code, recommendations generated, then **adversarially critiqued**
> (already built? real value? feasible?). 69 recommendations survived. Everything below is
> grounded in existing code — most of it is *surfacing and connecting* intelligence the
> engine already computes, not green-field building.

## The through-line

**The engine is the strength; the UI/API boundary is where value leaks out.** The product
already audits four AI engines + Google, scores goal-alignment, builds a gap model, generates
a strategy, materializes trackable tasks, AI-drafts compliance-screened content, and computes
learned-effectiveness levers, acceleration windows, and entrenchment-aware timelines — then
**throws much of that intelligence away at the boundary.** Three leverage points:

1. **Close the value-narrative loop.** Make `goal → gap → task → draft → published asset →
   per-prompt/per-engine score movement` *visible*. A monthly retainer renews only if the
   client SEES the needle move. Today the stated goal, per-prompt/per-engine trends, and the
   task→content→asset chain are all computed-but-hidden or absent.
2. **Build the local-reputation data layer.** There is **no GBP / review ingestion at all**,
   yet reviews are the most causal lever on both map-pack rank and the sentiment AI repeats.
   The strategy generator recommends review campaigns and the report lists review metrics —
   with zero data behind them.
3. **Turn on commerce & distribution.** A fully built, tested billing backend has **no UI**;
   quota blocks fail silently instead of prompting upgrade; content dead-ends with no outbound
   webhook to the client's GoHighLevel stack; per-tenant regulatory modeling is hardcoded-generic
   (a real liability for an RIA pilot).

---

## Top priorities (ranked, impact `i` / effort `e`)

| # | Recommendation | i/e | Dimension |
|---|----------------|-----|-----------|
| 1 | **Self-serve Plans & Billing page** — consume the already-built, tested billing backend (`/plans`, `/billing/checkout`, `/billing/portal`). A paying client currently cannot see their plan, usage, or buy more. | 5/M | Pricing |
| 2 | **Goal as the dashboard North Star** — `businesses.goal` is already in the payload but never rendered; show "Your goal: X" and frame the score as "how close AI is to saying this." | 5/S | Activation |
| 3 | **402/429 quota blocks → in-app upgrade modal** — the messages already name the plan/cap; today they show as a generic red error at peak purchase intent. | 4/S | Pricing |
| 4 | **Stitch the execution narrative** — link each task → the draft → the published asset it produced (FKs already exist; client-side join, no new endpoints). | 5/M | UX/IA |
| 5 | **GBP review ingestion** — the foundational local-reputation data layer (Serper already returns rating/ratingCount, currently discarded; score each review with the existing LLM sentiment scorer). | 5/L | Local SEO |
| 6 | **Per-prompt & per-engine TREND across runs** — metrics only compute the latest run; trend over time IS the product for a monthly retainer. | 5/M | AI reputation |
| 7 | **Outbound webhook bus** on every job + notification — one signed webhook into `notify()` and `run_job()`'s terminal block bridges GHL/Zapier/Make. | 5/M | Integrations |
| 8 | **Per-business regulatory profile** wired into every compliance gate — generic guessed disclosures are themselves a violation. | 5/L | Compliance |
| 9 | **Team roster with FK-backed assignees + workload view** — `assignee` is free text today; you can't run/scale a delivery team without per-person capacity. | 5/L | Service ops |
| 10 | **SLA / cadence breach alerts + cycle-time analytics** — `target_date/started_at/completed_at` are stamped but never read; this is the retention signal. | 5/M | Service ops |
| 11 | **Multi-surface distribution log** — turn the amplification *plan* into tracked per-channel publish records (`asset_placements`). | 5/L | Content |
| 12 | **Budget-abort made loud** — a budget cap currently surfaces as a bare red "failed"; make it a clear "you've hit your budget / here's how to get more" → self-serve upgrade. | 5/M | Reliability |

---

## Coverage gaps — what the domain obviously demands but the product does NOT yet handle

1. **No Google Business Profile / first-party review data of any kind.** For a local advisory SMB, the map pack and star rating ARE the local reputation, and reviews are the most causal input to both. The foundational data layer is entirely missing.
2. **No closed review-generation loop** (request → sent → landed) and **no review responses.** "Launch review sequence" is a static string with no workflow, copy, funnel, or way to reply to a negative Google review.
3. **Per-tenant regulatory modeling is absent** — compliance is hardcoded-generic. No `firm_type`, CRD, license-state, or required-disclosure fields; autofix *guesses* disclosures (itself a violation) and misfires for non-financial tenants.
4. **No auditable record of who approved/published** compliance-sensitive content. The gate blocks publish but records no immutable, attestable sign-off (FINRA 2210 / SEC recordkeeping).
5. **No crisis / time-sensitive event detection** beyond a single contested-rate threshold. No competitor-velocity alert, no regression cause hypothesis, no first-audit-ready trigger — though the signals are all captured.
6. **Trend over time is shallow** — per-prompt/per-engine movement is a single snapshot; nothing persists a per-run rollup, so trends are also fragile to answer pruning/re-scoring.
7. **The commercial layer is invisible to customers** — built/tested billing backend with no UI, no try-before-you-buy lead magnet.
8. **No real delivery-team ops layer** (capacity, SLA, audit trail) — yet the product IS a delivery team. Caps how many clients one operator can manage, i.e. gross margin.
9. **Content's last mile (distribution + publish) is untracked and manual** — briefs prescribe multi-surface amplification but the system records one `own_site` URL and no per-channel publish log.
10. **No outbound automation** to the client's existing stack (GHL/Zapier/Make) — everything dead-ends in the console and is hand-re-typed.
11. **Indefinite retention of unverified, potentially-defamatory third-party statements** with no PII handling — a GDPR/defamation + enterprise-security-review exposure.
12. **The score's own epistemic status is hidden** — no per-claim hallucination/fact-check, and the headline 0–100 weights hallucinated and web-cited answers identically with no confidence disclosure (the exact over-claiming the product polices, in its own hero metric).
13. **No pooled cross-client learning** — every account starts cold. Vertical-bucketed priors are the one asset a prompt-template competitor structurally cannot replicate — the defensibility moat, unbuilt.

---

## Themes (the 69 recs, clustered)

### 1. Make the value visible (the retention/renewal narrative)
Client-facing "this month's work" value panel (keep raw COGS admin-only); extend `ProgressStrip` with baseline-at-signup + share-of-voice change + acceleration-window delta, and tie the upgrade ask to that window ("Pro reaches your goal ~X months sooner"); in-console HTML report viewer (JSON over the existing `_load`); a "what we're tracking for you" profile readback; per-asset/per-channel correlational attribution.

### 2. Close the local-reputation loop (GBP & reviews)
Review velocity + rating trendline; AI-drafted compliance-screened review **responses** (treat each new review as a mention into the existing draft→approve flow, ordered by ascending stars); review-**request** loop orchestration (trackable funnel; defer automated send; hard guardrail against gating/incentivizing); GBP NAP-consistency checker (+ self-attested checklist for the rest); a data-driven "Local Reputation" report section.

### 3. Turn analytics into proactive intelligence & differentiation
Persist a per-run `run_metrics` rollup (alembic 0039) FIRST; **cross-business cohort calibration** (pooled priors by vertical + entrenchment band, k-anonymity — the moat); persona/location lens page; cross-engine divergence detector; regression attribution on score drops; competitor-velocity threat alerts; per-asset predicted-vs-realized ledger; surface the hidden `entrench_drag` + per-lever confidence/sample-count.

### 4. Run the agency: service ops, teams & multi-tenancy
Bulk task ops (after assignee FK); org self-serve access grant/revoke + a "manager" role tier (reuse the existing `/auth/invite`); change/audit trail; per-user notification prefs + digest batching; Slack/Teams channel sharing the webhook-bus config.

### 5. Trust, honesty & compliance as a sellable asset
Immutable compliance sign-off ledger (approver, flags, placeholders, body hash, override reason); span-level compliance flags + inline highlighting + store the pre-autofix body/diff; per-answer hallucination/fact-claim verification; grounding-aware score confidence badge; data-retention/PII purge job; consolidated methodology + honesty-disclaimer report appendix.

### 6. Activation, onboarding & first-value
Audit-complete re-engagement (`notify()` in-app + email with score + top gap + #1 step); outcome-promise success screen; setup completeness meter ("no geo → local rankings off"); domain-driven website pre-fill (net-new lightweight crawler, behind a flag); make every weak answer actionable (jump to the matching work order); scoped in-product education for the un-explained terms.

### 7. Console usability, navigation & growth motion
Responsive shell (hamburger drawer + a `ResponsiveTable` primitive for the raw tables); collapsible sidebar groups for the ~30-item rail; breadcrumbs + sharper imperative subtitles; fix incidents "sorted by urgency" (renders in raw order) and show `delay_impact` as a "cost of waiting"; outreach CRM seams (CSV export, Push-to-GHL, Draft-pitch); **free public "first audit" lead magnet** (isolated, hard cost-capped, cached); done-for-you concierge card + operator MRR/churn dashboard; one-click WordPress publish; content calendar (dated fields + overdue list first).

---

## Phased roadmap

### NOW (high-impact, S/M effort — mostly surfacing dormant code)
- Self-serve **Plans & Billing** page (consume the existing backend; gate on `org_role`)
- **Goal-vs-reality North Star** on the dashboard (render `businesses.goal`, reframe the score)
- **402/429 → upgrade modal** (after the billing page exists)
- **Stitch the execution narrative** (work order → draft → published asset, client-side join)
- **Budget-abort made loud** (typed `over_budget` result + banner + `budget_exhausted` alert)
- **SLA / cadence breach alerts** (`task_overdue`, `cadence_stalled` into `check_and_notify`)
- **Audit-complete re-engagement** `notify()` (first-audit-ready banner + email)
- **Outbound webhook bus** (into `notify()` + `run_job()` terminal block — unlocks GHL)
- Client-facing **"this month's work" value panel** (raw COGS stays admin-only)

### NEXT (the data-layer and ops foundations)
- **GBP review ingestion** (unblocks the whole local-reputation theme)
- **Regulatory profile** threaded into the compliance gate + autofix
- Persist **`run_metrics` rollup (alembic 0039)**, then per-prompt + per-engine **trend** charts
- **Team roster** (FK assignees + workload; assignee modal → dropdown)
- **Multi-surface distribution log** (`asset_placements` + per-surface Finalized checklist)
- Review velocity/rating trendline + AI-drafted compliance-screened **review responses**
- **Immutable compliance sign-off ledger** + override path
- Persona/location lens page + cross-engine divergence detector
- Regression attribution + competitor-velocity threat alerts
- **Responsive console shell** + incidents/gap severity ordering fix
- Outreach CRM seams (CSV, Push-to-GHL, Draft-pitch)
- In-console HTML report viewer + data-driven Local Reputation report section
- Onboarding: outcome-promise screen, completeness meter, actionable weak answers, profile readback

---

## Content Intelligence & Grounding (added 2026-06-24 — the content-quality program)

**Why:** Audit of the writer confirmed the content model received ONLY name/geo/services/title/instruction/target-query and was told to *write around* missing facts with `[INSERT:]` placeholders — no crawled-site grounding, **no keyword targeting at all** (keyword research was just a list of manual tools), and Serper's keyword-rich data (related searches, People-Also-Ask, autocomplete) untapped. Goal: content that is **grounded in real data** and carries **the language needed to rank and to be understood/cited by AI**.

### CI-1. Keyword Intelligence layer (NEXT — foundational, unblocks the rest)
A real keyword-targeting layer. New `keyword_research.py`: (a) **seed** candidate terms from the business profile + crawled site + competitor pages (LLM), (b) **ground/expand** with real Google data via the Serper key we already pay for — `relatedSearches`, `peopleAlsoAsk`, `/autocomplete`, and who actually ranks locally, (c) produce a ranked **target-keyword set per topic/page/geo** (primary, secondary, long-tail, local, question-keywords). Store in a new `target_keywords` table. New `keyword_research` job; wire into the gap/plan pipeline so each content work order carries its target keywords. Surface a "Keywords to rank for" view (per business + per content item) and feed GBP/local recs. *True search volume needs a paid API (DataForSEO/Keywords Everywhere) — optional enrichment, see CI-5.*

### CI-2. Grounded, RAG-style content generation (NEXT) — **first slice DONE**
Rework the generator to write from real data: crawled-site facts + the specific gap/narrative + the target keywords + brand voice, and route marquee long-form (article/FAQ/bio) to the **best model** (Opus `full` tier), not `mid`. **Shipped:** `content_generator._grounding_context()` now injects the latest site-crawl summary + gap model into the prompt; `GEN_SYSTEM` rewritten to ground in provided facts (not placeholders) and weave keywords; long-form bumped to `full`; keyword slot wired (fills when CI-1 lands). **Remaining:** multi-pass generation (keyword-mapped outline → draft → SEO/keyword self-check → compliance → revise); pull brand voice from approved prior assets; semantic retrieval of the most-relevant crawled pages (see CI-6).

### CI-3. Content scorecard / grounding verification (NEXT — extends the C5 draft-quality gate)
Make "does this actually have the language to move the needle" a checked fact. Extend `_evaluate` to score **keyword coverage** (are the primary/secondary/local/question keywords present and well-placed?), entity/topic coverage vs the crawl's `missing` entities, structure/schema, readability, and "answers the gap." Block/flag drafts missing the necessary language; show a **keyword checklist (included / missing)** + predicted SEO/AI lift in the draft-review UI.

### CI-4. Visual content generation (LATER)
AI **images / graphics / quote-cards / memes** for social, blog headers, and GBP posts via an image-model API — human-gated and compliance-safe (no AI images of real people or implied claims for a regulated firm). Short-form **video** stays brief-to-tool/templated for now (the briefs already exist); full generative video deferred. (Canva + image-gen integrations are an option.)

### CI-5. Search-volume enrichment (LATER, optional/paid)
Add real volume/difficulty to the keyword layer via DataForSEO / Keywords Everywhere. The LLM+Serper layer works without it; this only sharpens prioritization.

### CI-6. Semantic memory / pgvector (LATER)
Embed crawled pages + approved content so grounding retrieval is **semantic** (the `_already_covered` pgvector hook is already stubbed) — better page selection for RAG, plus content dedup.

### CI-7. Agentic content pipeline (LATER, optional)
A more autonomous research→outline→write→critique→revise loop with tools. **Recommendation: build native** (the existing in-process orchestrator + tool calls + job system + budget caps + pytest) rather than adopting LangGraph/LangChain — more controllable, testable, no heavy deps. LangGraph remains an option if a visual/branching agent graph is later desired.

---

### LATER (moat + strategic bets)
- **Cross-business cohort calibration** (k-anonymity) — build early so it compounds
- Per-answer **hallucination / fact-claim verification** (after the structured profile is solid)
- Data-retention purge job + PII redaction
- Review-request loop orchestration + GBP NAP checker
- Domain-driven website pre-fill onboarding (net-new crawler, flagged)
- Free public **first-audit lead magnet** + done-for-you concierge tier
- Per-asset/per-channel attribution, content funnel metrics, long→short repurpose engine
- Org self-serve access mgmt + "manager" role, bulk ops, audit trail, notif prefs, Slack/Teams
- One-click WordPress publish (Phase 1) / LinkedIn (deferred); inbound webhook for bidirectional GHL
- Operator MRR/expansion/churn dashboard + trial convert-or-churn nudges
- Judge-drift monitoring; awareness-vs-narrative driver labels; surface `entrench_drag`; impact ledger; coverage-breadth audit; content calendar grid; education tooltips; span-level compliance highlighting; grounding-aware score confidence; methodology/disclaimer appendix; sidebar collapse + breadcrumbs; dormant-account nudge
