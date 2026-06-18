# Reputation Console — Replit demo

A one-click, full-stack demo a customer can click through: the **Next.js console** + the
**FastAPI API** + **Postgres**, pre-seeded with a real audit (the "Team Unstoppable"
pilot — what ChatGPT, Claude, Perplexity, and Gemini say about the business, the gaps, the
action plan, the timeline, and the rankings).

## Run it on Replit

1. **Import this GitHub repo** into Replit (Create → Import from GitHub →
   `asbuyrylw/Reputation_Management`).
2. Press **Run**. The first boot takes a few minutes (it installs dependencies, starts
   Postgres, loads the demo data, builds the console). Subsequent runs are fast.
3. Open the web preview and **log in**:

   | | |
   |---|---|
   | **Email** | `owner@teamunstoppable.com` |
   | **Password** | `TeamUnstoppable2026!` |

   (An admin account `admin@local` / `DemoAdmin!234` is also seeded.)

That's it — every page is populated with the seeded audit data.

## What's running (and why it's one URL)

`replit/start.sh` brings up three things and exposes **only the console** publicly:

```
Browser ──HTTPS──▶ Next.js console (public :80/3000)
                      │  /api/*  ──proxy──▶  FastAPI API (127.0.0.1:8000)
                      │                          │
                      └── pages (/dashboard…)    └──▶ Postgres (127.0.0.1:5432, pre-seeded)
```

Replit exposes a single public port, so the console proxies `/api/*` to the local API
(`reputation-console/next.config.ts` → `rewrites`). Because that's **same-origin**, the
httpOnly session cookie and CSRF token work with no CORS setup.

## Notes

- **No AI keys needed for the demo.** Browsing the seeded data needs nothing. You only need
  real `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `PERPLEXITY_API_KEY` / `GEMINI_API_KEY`
  (set them as Replit Secrets) to run a **brand-new** audit from the Admin → Run jobs page.
- **The demo data lives in `reputation_engine/demo/seed_data.sql`** and is loaded only on
  first boot (when the database is empty). Delete the repl's `.pgdata/` folder to reseed.
- **Change the demo passwords** for anything public-facing: set `ADMIN_SEED_PASSWORD` (and
  re-seed users) and a strong `JWT_SECRET` as Replit Secrets.
- **To force a console rebuild** (e.g., after pulling new code): delete
  `reputation-console/.next/` and press Run.

## Local equivalent (not Replit)

```bash
bash replit/start.sh        # needs postgres, python3, node on PATH
# or run the pieces yourself — see DEPLOY.md and docker-compose.yml
```

## Architecture recap

- **Console** (`reputation-console/`) — Next.js 16 / React 19; pure frontend, all data via the API.
- **API** (`reputation_engine/rep_engine/api/`) — FastAPI; reads/writes Postgres, runs jobs.
- **Engine** (`reputation_engine/rep_engine/`) — the audit/scoring/strategy pipeline.

See `DEPLOY.md` for a production (split) deployment where the console and API are hosted separately.
