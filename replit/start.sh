#!/usr/bin/env bash
# One-command full-stack demo for Replit: Postgres + FastAPI API + Next.js console,
# pre-seeded with the Team Unstoppable demo data. The console is the only public port; it
# proxies /api/* to the local API (see reputation-console/next.config.ts), so the session
# cookie + CSRF work same-origin with no CORS. View-only demo: no AI keys are needed to
# browse the seeded data (you'd only need keys to run a brand-new audit).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PGPORT="${PGPORT:-5432}"
PGDATA="$ROOT/.pgdata"
DB=reputation
DSN="postgresql://postgres:postgres@127.0.0.1:${PGPORT}/${DB}"
PSQL="psql -h 127.0.0.1 -p ${PGPORT} -U postgres"

echo "▶ [1/4] Starting Postgres…"
if [ ! -d "$PGDATA/base" ]; then
  initdb -D "$PGDATA" -U postgres --auth=trust >/dev/null
fi
pg_ctl -D "$PGDATA" -o "-c listen_addresses=127.0.0.1 -p ${PGPORT}" -l "$ROOT/.pglog" -w start >/dev/null 2>&1 \
  || pg_ctl -D "$PGDATA" status >/dev/null 2>&1 \
  || { echo "  ! Postgres failed to start:"; tail -20 "$ROOT/.pglog" 2>/dev/null; exit 1; }
for _ in $(seq 1 30); do pg_isready -h 127.0.0.1 -p "${PGPORT}" -U postgres >/dev/null 2>&1 && break; sleep 1; done
$PSQL -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}'" | grep -q 1 \
  || $PSQL -c "CREATE DATABASE ${DB}" >/dev/null

echo "▶ [2/4] Backend deps + schema + demo data…"
if [ ! -d "$ROOT/.venv" ]; then python3 -m venv "$ROOT/.venv"; fi
PY="$ROOT/.venv/bin/python"
"$ROOT/.venv/bin/pip" install --quiet --disable-pip-version-check -r reputation_engine/requirements.txt
export REP_DB_DSN="$DSN"
( cd reputation_engine && "$PY" -m alembic upgrade head )
ROWS=$($PSQL -d "${DB}" -tAc "SELECT COUNT(*) FROM businesses" 2>/dev/null || echo 0)
if [ "${ROWS:-0}" = "0" ]; then
  echo "  loading demo seed (Team Unstoppable)…"
  $PSQL -d "${DB}" -q -f reputation_engine/demo/seed_data.sql
else
  echo "  demo data already present (businesses=${ROWS}) — skipping seed."
fi

echo "▶ [3/4] Starting API on 127.0.0.1:8000…"
export JWT_SECRET="${JWT_SECRET:-demo-only-secret-change-me-0123456789abcdef0123}"
export ADMIN_SEED_EMAIL="${ADMIN_SEED_EMAIL:-admin@local}"
export ADMIN_SEED_PASSWORD="${ADMIN_SEED_PASSWORD:-DemoAdmin!234}"
export COOKIE_SECURE="${COOKIE_SECURE:-1}"
export COOKIE_SAMESITE="${COOKIE_SAMESITE:-lax}"
export JOB_WORKER=inline
( cd reputation_engine && "$ROOT/.venv/bin/python" -m uvicorn rep_engine.api.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null; pg_ctl -D "$PGDATA" stop >/dev/null 2>&1' EXIT INT TERM
for _ in $(seq 1 40); do curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done

echo "▶ [4/4] Building + serving the console on 0.0.0.0:${PORT:-3000}…"
cd "$ROOT/reputation-console"
export NEXT_PUBLIC_API_BASE_URL=/api          # build-time: console fetches same-origin /api/*
export API_PROXY_TARGET=http://127.0.0.1:8000 # runtime: Next proxies /api/* -> the API
if [ ! -d node_modules ]; then npm install; fi
if [ ! -f .next/BUILD_ID ]; then npm run build; fi
echo ""
echo "  ✅ Demo ready. Log in as:  owner@teamunstoppable.com  /  TeamUnstoppable2026!"
echo ""
npm run start -- -p "${PORT:-3000}" -H 0.0.0.0
