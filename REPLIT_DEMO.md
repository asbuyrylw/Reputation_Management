# Reputation Console — Replit demo

A one-click, full-stack demo a customer can click through: the **Next.js console** + the
**FastAPI API** + **Postgres**, pre-seeded with the **current** Team Unstoppable pilot data —
what ChatGPT, Claude, Perplexity, and Gemini say about the business, the gaps, the **75-task
action plan**, the timeline, the rankings, the citations, and live web mentions.

> The seed (`reputation_engine/demo/seed_data.sql`) is a snapshot of the working database, so
> the demo shows the **same data you see locally**. Regenerate it any time with the one-liner at
> the bottom.

## Run it on Replit (recommended for a live demo)

1. **Import this GitHub repo** into Replit (Create → Import from GitHub →
   `asbuyrylw/Reputation_Management`). Pick the branch you pushed (see "Publishing" below).
2. Press **Run**. First boot takes a few minutes (installs deps, starts Postgres, migrates the
   schema, loads the demo data, builds the console). Later runs are fast.
3. Open the web preview and **log in**:

   | Role | Email | Password |
   |---|---|---|
   | **Client (Team Unstoppable)** | `owner@teamunstoppable.com` | `TeamUnstoppable2026!` |
   | **Admin** (all businesses, Run-jobs page) | `admin@local` | `DemoAdmin!234` |

   The client login is the realistic Director view — pinned to Team Unstoppable, can view
   everything and trigger jobs. The admin login adds the Admin → Run jobs / Businesses pages.

Every page is populated with the current data out of the box — **no AI keys are needed just to
browse**.

## To run audits / jobs LIVE in the demo (optional)

Running a **brand-new** audit/benchmark/etc. (the buttons on the Run-jobs page, Competitors,
Local rankings, Mentions, etc.) calls the AI providers, so it needs API keys **and** a runtime
that lets a multi-minute background job finish. Two things:

1. **Set API keys as Replit Secrets** (Tools → Secrets): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `SERPER_API_KEY` (local rankings + wider mentions), and optionally `PERPLEXITY_API_KEY`,
   `GEMINI_API_KEY`. Also set a strong `JWT_SECRET` and change `ADMIN_SEED_PASSWORD`.
2. **Pick the right runtime for long jobs.** Jobs run *inline* in the API process
   (`JOB_WORKER=inline`), so they only survive while that process stays alive:
   - **Pressing "Run" in the editor** keeps the process warm while you're actively using it —
     fine for triggering a job and watching it during a live demo.
   - A **published Autoscale/Cloud Run deployment scales to zero between requests and will kill a
     long background job mid-run.** For a stable URL that can run audits, deploy as a
     **Reserved VM** instead (always-on), or run the worker as a second process.
   - **Demo tip:** to show "click a button → watch it work" reliably, trigger a *fast* job —
     **Suggest prompts**, **Refresh AI citations**, or **Check local search rankings** finish in
     well under a minute. A full audit takes several minutes and ~$4 in API spend, so it's best
     **pre-run** (already in the seed) unless you're on a Reserved VM.

## What's running (and why it's one URL)

`replit/start.sh` brings up three things and exposes **only the console** publicly:

```
Browser ──HTTPS──▶ Next.js console (public :80/3000)
                      │  /api/*  ──proxy──▶  FastAPI API (127.0.0.1:8000, JOB_WORKER=inline)
                      │                          │
                      └── pages (/dashboard…)    └──▶ Postgres (127.0.0.1:5432, pre-seeded)
```

Replit exposes a single public port, so the console proxies `/api/*` to the local API
(`reputation-console/next.config.ts` → `rewrites`). Because that's **same-origin**, the httpOnly
session cookie and CSRF token work with no CORS setup.

## Publishing this to GitHub (push, don't zip)

**Push to GitHub and import — it's cleaner than a zip** (versioned, one-click re-deploys when you
push new code, no re-upload). The repo is already wired to `asbuyrylw/Reputation_Management`.

- Commit + push the branch you want to demo (e.g. `feature/premium-ui-redesign`), then in Replit
  choose that branch on import. To redeploy after a code change: push, then in Replit `git pull`
  + press Run (delete `reputation-console/.next/` to force a rebuild).
- **Heads-up on data + secrets:** `reputation_engine/demo/seed_data.sql` contains the Team
  Unstoppable demo data and is committed to the repo — keep the **repo private** for a client
  demo. Real API keys are **never** committed (`.env` is gitignored); set them as Replit Secrets.

## Notes

- **Reseed:** the demo data loads only on first boot (when the DB is empty). Delete the repl's
  `.pgdata/` folder to reload it.
- **Change the demo passwords** for anything public-facing (set `ADMIN_SEED_PASSWORD` + a strong
  `JWT_SECRET` as Secrets; the client password is in `reputation_engine/demo/demo_extras.sql`).
- **Force a console rebuild** after pulling new code: delete `reputation-console/.next/`, press Run.

## Regenerate the demo seed from the current database

```bash
# from reputation_engine/, with the live DB running (REP_DB_DSN points at it):
docker exec rep_pg_test pg_dump -U postgres --data-only --no-owner --no-privileges \
  --exclude-table=alembic_version --exclude-table=users --exclude-table=business_access \
  --exclude-table=api_jobs --exclude-table=audit_log --exclude-table=auth_tokens \
  reputation_dev > reputation_engine/demo/seed_data.sql
```
(Auth/ops tables are excluded so no real password hashes leak; the demo login is created fresh by
`demo/demo_extras.sql`, and `start.sh` re-seeds the admin. Schema comes from `alembic upgrade head`.)

## Architecture recap

- **Console** (`reputation-console/`) — Next.js 16 / React 19; pure frontend, all data via the API.
- **API** (`reputation_engine/rep_engine/api/`) — FastAPI; reads/writes Postgres, runs jobs.
- **Engine** (`reputation_engine/rep_engine/`) — the audit/scoring/strategy pipeline.

See `DEPLOY.md` for a production (split) deployment where the console and API are hosted separately.
