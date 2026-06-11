# Reputation Crowding-Out Engine

An end-to-end, AI-driven system that audits how AI assistants and search describe
a business, finds the gaps, and produces a dated strategic plan with work orders to
**out-produce and out-corroborate accurate, positive content** so it dominates what
gets surfaced.

> **Method = crowding-out, not suppression.** This system never tries to delete,
> hide, or manipulate legitimate third-party views (e.g., a contested "MLM" label).
> It measures where the accurate narrative is thin and helps you publish and
> corroborate enough true, well-structured content that the good is what surfaces
> first. That boundary is enforced in the prompts and the generated plan.

Works for **any business across any domain** — multi-tenant by design.

---

## Architecture

```
intake ─► AI-state audit ─► site crawl ─► gap model ─► strategy plan ─► report
          (Module 1)        (Module 3)    (Module 1)    (Module 2)       (Module 4)
                         orchestrator wires these in order
```

| Module | File | Does |
|--------|------|------|
| 1 | `rep_engine/ai_state_audit.py` | Runs a per-business prompt battery across Perplexity / OpenAI-search / Anthropic / Gemini, scores each answer (sentiment, goal alignment, contested mentions, owned-content surfacing), stores runs, diffs them, and emits the **structured gap model**. |
| 2 | `rep_engine/strategy_generator.py` | Turns the gap model into a **phased, dated plan** with work orders classified `auto`/`semi`/`manual`, each assigned a best-fit tool from the registry. |
| 3 | `rep_engine/site_crawl.py` | Crawls the business's own domain (titles, meta, headings, schema, thin content) plus an optional open-source Lighthouse pass, and **merges findings into the gap model**. |
| 4 | `rep_engine/report_generator.py` | Generates the client-facing **monthly `.docx` report** — executive summary, trend charts, **before/after answer snippets**, work-order status, and the correlational attribution narrative. The renewal driver. |
| 5 | `rep_engine/tracking.py` | **Execution + attribution layer.** Materializes the plan into tracked work orders (status lifecycle), records published assets, correlates metric movement with assets shipped, and fires contested-spike alerts. This is what makes it a *retainer*, not a one-time plan. |
| 6 | `rep_engine/content_generator.py` | **AI content generator.** Turns generatable work orders into finished DRAFTS (FAQ, schema, article, bio, GBP post, review-request) with self-eval + auto-revision, a compliance gate, and human-approval-only promotion to `assets`. Never auto-publishes. |
| 7 | `rep_engine/timeline_estimator.py` | **Timeline estimator.** Range-based projection (optimistic/expected/conservative) for how long until the accurate narrative dominates, from entrenchment + plan throughput + this business's own observed velocity. Always a projection with explicit confidence; never a promise; drown-out not removal. |
| 8 | `rep_engine/acceleration_advisor.py` | **Acceleration advisor.** Models how specific quantities of third-party/human levers (articles, earned links, videos, press, genuine reviews, podcasts) compress the timeline; ranks levers by impact and bundles light/moderate/aggressive scenarios. Range-based projection with a realism cap; genuineness/compliance guardrails. |
| 9 | `rep_engine/feedback_loop.py` | **Outcome feedback loop.** Learns, per business, how much each lever type actually moved goal_alignment across run-windows; writes learned effectiveness + baseline that recalibrate the estimator and advisor away from generic defaults. Confidence rises with sample size; correlation not proof. |
| 10 | `rep_engine/citation_analytics.py` | **Citation analytics (share of voice).** Which domains AI engines cite about the business, how that shifts run-over-run (momentum: rising/falling/new/dropped), and how it differs by asker persona and location. Classifies owned/neutral/contested; measurement only, never fabricates citations. |
| — | `rep_engine/cost.py` | Per-call **cost ledger + monthly budget caps** so audits can't run away and you know your COGS per client. |
| — | `rep_engine/orchestrator.py` | One command runs the whole pipeline (`run`, optionally `--generate-drafts`) or the monthly re-cycle (`cycle`: audit → gap → attribution → alert → report). |

### Tool registry (Module 2)
The registry is an **available toolbox, not a mandate**. Each capability lists
candidate tools (open-source, API, and AppSumo lifetime-deal tools) ranked
auto → semi → manual. The generator picks the most-automatable fit and only
assigns an AppSumo tool when it genuinely helps (e.g., video, media lists,
fact-checking). Flip any tool off with its `enabled` flag.

---

## Setup

```bash
# 1. Python deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Database (Postgres) -- the schema is managed by Alembic (single source of truth,
#    replacing the old hand-applied schema.sql + schema_v2..v9.sql files).
createdb reputation                      # or use an existing instance
alembic upgrade head                     # builds/updates the full schema  (or: make migrate)

# 3. Config
cp .env.example .env                      # then fill in keys
export $(grep -v '^#' .env | xargs)

# 4. (optional) open-source technical audit
npm install -g lighthouse
```

---

## Run

```bash
# Full pipeline for a new business
# Preflight check before the FIRST live run (validates DB, keys, engine shapes; minimal spend)
python -m rep_engine.preflight --business-id 1

python -m rep_engine.orchestrator run \
  --name "Team Unstoppable" --domain teamunstoppable.com \
  --services "life insurance, retirement, debt elimination" \
  --goal "Dominate local Cincinnati branded queries with accurate narrative" \
  --contested "MLM,pyramid scheme,scam" --geo "Cincinnati OH" \
  --start 2026-06-09 --max-pages 40

# Monthly re-run for an existing business (audit -> gap -> attribution -> alert -> report)
python -m rep_engine.orchestrator cycle --business-id 1
# resume an interrupted cycle (skips completed steps, no re-spend):
python -m rep_engine.orchestrator cycle --business-id 1 --resume

# Execution tracking (the retainer system of record)
python -m rep_engine.tracking sync-plan  --business-id 1          # plan -> tracked work orders
python -m rep_engine.tracking set-status --wo 12 --status done --assignee "VA"
python -m rep_engine.tracking log-asset  --business-id 1 --type owned_page \
    --title "How we protect families" --url https://... --surface own_site --wo 12
python -m rep_engine.tracking attribute   --business-id 1         # assets -> metric movement
python -m rep_engine.tracking check-alert --business-id 1         # contested-spike alert
python -m rep_engine.tracking status      --business-id 1         # program % complete

# Individual modules also run standalone:
python -m rep_engine.ai_state_audit add-business --name "..." --domain "..." --goal "..."
python -m rep_engine.ai_state_audit audit --business-id 1
python -m rep_engine.ai_state_audit gap-model --business-id 1
python -m rep_engine.site_crawl crawl --business-id 1 --max-pages 40
python -m rep_engine.strategy_generator plan --business-id 1 --start 2026-06-09
python -m rep_engine.strategy_generator tools        # list the registry
python -m rep_engine.report_generator monthly --business-id 1

# Content generation (Module 6 -- drafts only, human approves)
python -m rep_engine.content_generator generate --business-id 1 --wo 12
python -m rep_engine.content_generator list --business-id 1
python -m rep_engine.content_generator approve --draft 5 --reviewer "Logan"
python -m rep_engine.content_generator reject  --draft 5 --reviewer "Logan" --notes "off-brand"

# Timeline estimate (Module 7 -- range-based projection, not a promise)
python -m rep_engine.timeline_estimator estimate --business-id 1

# Ways to accelerate (third-party levers; ranges, not promises)
python -m rep_engine.acceleration_advisor advise --business-id 1

# Outcome feedback loop (learns what worked; recalibrates the above)
python -m rep_engine.feedback_loop learn --business-id 1
python -m rep_engine.feedback_loop show  --business-id 1

# Citation analytics (share of voice, momentum, persona/location lenses)
python -m rep_engine.citation_analytics analyze  --business-id 1
python -m rep_engine.citation_analytics momentum --business-id 1
python -m rep_engine.citation_analytics personas --business-id 1
```

---

## Automation / scheduling (recommended: self-hosted n8n)

- Schedule `orchestrator cycle` monthly per client (n8n Cron node → Execute Command).
- Route `auto` work orders to API calls; push `semi`/`manual` work orders to a
  task board (Trello/Notion/Dart) or a VA queue via n8n.
- n8n is open-source and self-hostable next to your Postgres; Make.com is the paid
  alternative if you prefer zero ops overhead.

---

## Placeholder index

Search the code for these. Most are also settable via `.env`.

| Code | Where | Meaning |
|------|-------|---------|
| PH 1 | all modules | `REP_DB_DSN` Postgres connection |
| PH 2 | ai_state_audit | `ORCHESTRATOR` choice (anthropic/openai); CRAWL_UA in site_crawl |
| PH 3–4 | ai_state_audit | Anthropic / OpenAI keys |
| PH 5–6 | ai_state_audit | Perplexity / Gemini keys |
| PH 7–8 | ai_state_audit | Orchestrator model IDs |
| PH 9 | ai_state_audit | Perplexity model name |
| PH 10 | ai_state_audit | OpenAI Responses + web_search request shape (verify current) |
| PH 11 | ai_state_audit | Anthropic web_search tool block (optional grounding) |
| PH 12 | ai_state_audit | Gemini search-grounding tool |
| PH 1 | strategy_generator / site_crawl / report_generator / orchestrator | `REP_DB_DSN` |
| PH 2 | report_generator | `REP_OUTPUT_DIR` |

> Note: the answer-engine and OpenAI/Gemini search APIs change their request
> shapes periodically. Each engine is isolated in one adapter method — update only
> that method against current docs when wiring keys.

---

## Semantic-depth analysis

Each crawled page gets a **citation-readiness score (0-100)** based on signals 2026 GEO research links to AI citation: entity/topic coverage, title-to-query alignment, front-loading (first 30%), freshness, lexical breadth, and question coverage. Backlinks and schema are deliberately excluded from the score (studies found they don't move AI citations). Missing entities feed the gap model as content opportunities.

## Mention monitoring + reply drafting (unlimited)

Monitor mentions of any business/keyword across pluggable sources (Reddit, Google News RSS built in; register your own) — **no per-business license cap**. Drafts on-brand replies via the content generator + compliance gate. **Nothing is auto-posted**: every reply is `pending_review` for human approval.

```bash
python -m rep_engine.mention_monitor add --business-id 1 --keyword "Acme Financial"
python -m rep_engine.mention_monitor discover --business-id 1
python -m rep_engine.mention_monitor draft --business-id 1
python -m rep_engine.mention_monitor pending --business-id 1
python -m rep_engine.mention_monitor approve --reply 5 --reviewer "Logan"
```

## Competitor benchmarking

Register competitors for a business, run the same prompt battery, and compare **appearance rate** — the share of category questions where each name is mentioned or its site is cited. The report shows where you rank and the biggest opportunity (questions a rival appears in but you don't).

```bash
python -m rep_engine.competitor add --business-id 1 --name "Rival LLC" --domain rival.com
python -m rep_engine.competitor benchmark --business-id 1
python -m rep_engine.competitor compare --business-id 1
```

## Cost levers & input quality

- **Firecrawl fetch** (`FIRECRAWL_API_KEY`, `CRAWL_FIRECRAWL_MODE=auto`): the crawler re-fetches fully-rendered HTML for client-side-rendered pages so JS sites aren't audited as near-empty. `auto` only spends a Firecrawl credit when a page looks thin.
- **Tiered model routing**: the high-volume per-answer scoring pass uses a cheap model (`ORCH_MODEL_*_CHEAP`), while gap-model synthesis and content generation use the full model.
- **Adaptive sampling** (`CRAWL_ADAPTIVE_SAMPLING=1`): `samples_per_prompt` is treated as a max; sampling stops early once a prompt's scores are stable and clear of the decision boundary, so samples are spent where they change the picture. Both levers are reflected in the cost ledger.

## Configuration & logging

All settings are read from env and validated at startup by `config.py` (Pydantic v2): bad DSNs, out-of-range thresholds, or an orchestrator whose key isn't set are caught with one clear message rather than a mid-run failure. `logging_setup.py` tags every log line with `business_id` + `run_id` (set `REP_LOG_JSON=1` for JSON lines), so multi-client runs are filterable.

## Robustness (production hardening)

- **Resilient HTTP (`http.py`):** every provider call retries on 429/5xx/timeouts with
  exponential backoff + jitter, honors `Retry-After`, and returns a result that
  **distinguishes a failed call from a genuinely empty answer**. Failed datapoints are
  stored with NULL metrics and a `failed` flag so they never drag audit averages down.
- **Structured outputs:** the orchestrator LLM uses provider JSON modes (OpenAI
  `response_format=json_object`; Anthropic JSON-only + assistant prefill) so gap-model
  parsing is reliable, with a lenient parser as a safety net.
- **Crawler:** uses `selectolax` for robust HTML parsing (falls back to regex if not
  installed), and **respects `robots.txt`** by default (`CRAWL_RESPECT_ROBOTS=0` to disable).
- **Multi-sampling:** each prompt runs N times per engine (`samples_per_prompt`) and
  metrics average across samples to reduce LLM run-to-run noise.

## What's not automated (by design)

- **Reddit / community participation** must be genuine, human, value-add, and
  disclosed — never automated reputation posting (policy + ban risk).
- **Most AppSumo video/content tools** have no usable API; the system emits a
  specific work order and a human operates the tool.
- **Local press** depends on editors — treat as upside, not a fixed deliverable.

This is the human-in-the-loop layer, surfaced explicitly in every plan.
```
