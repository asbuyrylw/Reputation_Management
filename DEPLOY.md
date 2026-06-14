# Reputation Console — run & deploy

Two pieces: the **FastAPI backend** (`reputation_engine/rep_engine/api/`) and the
**Next.js console** (`reputation-console/`). They talk over HTTP; the engine CLI is
untouched.

## Run locally (no Docker)

```bash
# 1) API + worker (terminal A) — needs the engine's Postgres + an Anthropic key for audits
cd reputation_engine
export REP_DB_DSN=postgresql://postgres:postgres@localhost:5432/reputation \
       JWT_SECRET=$(openssl rand -hex 32) \
       ADMIN_SEED_EMAIL=admin@local ADMIN_SEED_PASSWORD=change-me \
       API_CORS_ORIGINS=http://localhost:3000
alembic upgrade head                       # apply migrations (incl. 0007 auth, 0008 jobs)
python -m uvicorn rep_engine.api.main:app --reload          # http://localhost:8000
# Durable background jobs (optional, terminal A2): JOB_WORKER defaults to 'inline' for dev.
# For production set JOB_WORKER=worker and run:  python -m rep_engine.api.worker

# 2) Console (terminal B)
cd reputation-console
npm install
npm run dev                                # http://localhost:3000 — log in with the seed admin
```

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
- **Hardening still to add**: move the SPA token from localStorage to an httpOnly
  refresh cookie, add request/audit logging of writes + triggers, and a login
  rate-limit. These are tracked as the remaining deploy-readiness items.
