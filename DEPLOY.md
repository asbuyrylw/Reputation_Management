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
- **Hardening done**: the API sets an **httpOnly `rc_token` cookie** on login and
  accepts it for auth (defense-in-depth vs. XSS token theft); **every write/trigger is
  audit-logged** (`audit_log` table, via middleware, attributed to the acting user); and
  **login is rate-limited** (per-IP sliding window).
- **Hardening remaining**: switch the SPA to cookie-only auth (drop the localStorage
  bearer) + add CSRF protection; ship the rate-limit via a shared store for multi-process
  deployments. (The backend already supports cookie auth, so this is a frontend slice.)
