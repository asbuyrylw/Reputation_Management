# Reputation Console — run & deploy

Two pieces: the **FastAPI backend** (`reputation_engine/rep_engine/api/`) and the
**Next.js console** (`reputation-console/`). They talk over HTTP; the engine CLI is
untouched.

## Run locally

Config lives in **`reputation_engine/.env`** (REP_DB_DSN, JWT_SECRET, ADMIN_SEED_EMAIL,
ADMIN_SEED_PASSWORD, API_CORS_ORIGINS, JOB_WORKER). The API **auto-loads that .env,
auto-runs migrations, and seeds the admin on startup** — so there is no separate env-export
or `alembic` step. (.env is gitignored; ANTHROPIC_API_KEY there enables audits.)

**Windows PowerShell** (two terminals):

```powershell
# 1) API  (terminal A)
cd reputation_engine
python -m uvicorn rep_engine.api.main:app --reload     # http://localhost:8000

# 2) Console  (terminal B)
cd reputation-console
npm install        # first time only
npm run dev        # http://localhost:3000 — log in with ADMIN_SEED_EMAIL / ADMIN_SEED_PASSWORD
```

macOS/Linux is identical (same two commands). For durable background jobs set
`JOB_WORKER=worker` in `.env` and run a third process: `python -m rep_engine.api.worker`
(with `AGENT_CHECKPOINT_PG=1` so human-gated agent reviews resume across processes).

## Run the backend with Docker

```bash
JWT_SECRET=$(openssl rand -hex 32) ADMIN_SEED_PASSWORD=change-me docker compose up --build
# api  -> http://localhost:8000   (runs migrations on start; seeds the admin)
# worker runs durable background jobs; AGENT_CHECKPOINT_PG=1 enables human-gate resume
```

## Deploy notes (Phase 5 readiness; ratchet before public exposure)

- **Console**: deploy `reputation-console/` to Vercel (or any Node host); set
  `NEXT_PUBLIC_API_BASE_URL` to the API URL.
- **API**: set a strong `JWT_SECRET`, lock `API_CORS_ORIGINS` to the console origin,
  use a managed Postgres, and run the **worker** process (`JOB_WORKER=worker`) so
  long jobs survive web restarts and human-gated agent reviews can resume
  (`AGENT_CHECKPOINT_PG=1`).
- **REQUIRED over HTTPS — set `COOKIE_SECURE=1`.** This adds the `Secure` flag to the
  session + CSRF cookies so they are never sent in cleartext. Also set `COOKIE_SAMESITE`:
  `strict` when the console and API share a registrable domain (e.g. `app.acme.com` +
  `api.acme.com`), or `none` when they are different sites (cross-site cookies require
  `Secure`, which is forced on automatically for `none`). Defaults (unset `COOKIE_SECURE`,
  `COOKIE_SAMESITE=lax`) are for local http dev only. The dev runner binds `127.0.0.1` by
  default; set `API_HOST=0.0.0.0` (and optionally `API_PORT`) for container/host exposure.
- **Engine model ids**: `GEMINI_MODEL` defaults to a current model (the 1.5 line is
  retired); `PERPLEXITY_MODEL` defaults to `sonar`. Verify each id against your account's
  live model list — `preflight_engines()` logs the active ids and fails loudly before a
  paid audit if nothing is configured.
- **Verified-retrieval grounding (Phase 1, ON by default)**: answer engines query the LIVE
  web so the audit measures what AI assistants actually surface, not stale model memory —
  Anthropic `web_search`, Gemini `google_search`, OpenAI Responses `web_search` (Perplexity
  `sonar` is grounded by design). Each answer records a `grounded` flag, and
  `GET /businesses/{id}/per-engine` reports per-engine KPIs with sample sizes, confidence
  intervals, grounding coverage, and a partial-coverage flag. **Anthropic web search must be
  enabled by the org admin in the Claude Console**, and Gemini/OpenAI need real keys; set
  `ENGINE_GROUNDING=0` as a fallback to disable grounding for a provider that isn't
  provisioned yet (answers then come from model memory and are flagged ungrounded).
- **Billing/plans (Phase 2b)**: the plan catalog (Starter/Growth/Pro/Agency) is seeded
  idempotently from the COGS model at startup (`billing.seed_plans`); prices are COGS-derived
  proposals — review/adjust them. An **organization** carries one subscription; the job-trigger
  chokepoint enforces **per-org quotas** (monthly audits) and **active-subscription**, returning
  429 (over quota) / 402 (inactive). Backward-compatible: a business with no org, or an org with
  no subscription, is **unmetered**. Assign a plan via `POST /admin/organizations/{id}/subscription`.
- **Stripe (Phase 2c)**: set `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and a price id per
  plan (`STRIPE_PRICE_STARTER/GROWTH/PRO/AGENCY`, mapped into `plan_catalog.stripe_price_id` at
  startup), plus `APP_BASE_URL` for Checkout success/cancel + Portal return URLs. Org owners hit
  `POST /billing/checkout` (Stripe Checkout) and `POST /billing/portal` (Customer Portal); point
  the Stripe webhook at `POST /billing/webhook` (signature-verified + idempotent — drives
  subscription status: checkout→active, subscription.updated→mirrored, deleted→canceled,
  payment_failed→past_due). The `stripe` SDK is imported lazily, so the app runs without it until
  `STRIPE_SECRET_KEY` is set (the billing endpoints return 503 until then). Headline prices are
  value-based ($99/$299/$899/$2499); the COGS model is the margin floor/guardrail.
- **Hardening done**: **cookie-only SPA auth** (httpOnly `rc_token`, no browser token
  storage) with **double-submit CSRF** on writes; env-driven **Secure + SameSite** cookies;
  baseline **security headers** (HSTS when secure, `nosniff`, `frame-ancestors 'none'`,
  `no-store`); **every write/trigger is audit-logged** (`audit_log`, attributed to the
  acting user); **login is rate-limited** (per-IP sliding window).
- **Hardening remaining** (Phase 3 in `PRODUCTION_READINESS.md`): ship the rate-limit via
  a shared store for multi-process deployments; add the `__Host-` cookie prefix; stuck-job
  reaper + worker resilience; error tracking + metrics/alerting; backups/PITR.
