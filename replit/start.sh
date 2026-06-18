#!/usr/bin/env bash
# One-command full-stack demo for Replit: Postgres + FastAPI API + Next.js console,
# pre-seeded with the Team Unstoppable demo data. The console is the only public port; it
# proxies /api/* to the local API (see reputation-console/next.config.ts), so the session
# cookie + CSRF work same-origin with no CORS. View-only demo: no AI keys are needed to
# browse the seeded data (you'd only need keys to run a brand-new audit).
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PGPORT="${PGPORT:-5432}"
PGDATA="$ROOT/.pgdata"
DB=reputation
DSN="postgresql://postgres:postgres@127.0.0.1:${PGPORT}/${DB}"

# Always specify -d postgres for admin connections to avoid PGDATABASE env var interference
PSQL_ADMIN="psql -h 127.0.0.1 -p ${PGPORT} -U postgres -d postgres"
PSQL_DB="psql -h 127.0.0.1 -p ${PGPORT} -U postgres -d ${DB}"

echo "▶ [1/4] Starting Postgres…"
mkdir -p /run/postgresql

# Initialize data directory if needed
if [ ! -d "$PGDATA/base" ]; then
  initdb -D "$PGDATA" -U postgres --auth=trust >/dev/null
fi

# Clean up stale lock/pid files from previous runs so pg_ctl can start cleanly
rm -f "$PGDATA/postmaster.pid"
rm -f "/run/postgresql/.s.PGSQL.${PGPORT}" "/run/postgresql/.s.PGSQL.${PGPORT}.lock"

# Start Postgres (or verify it's already running)
pg_ctl -D "$PGDATA" \
  -o "-c listen_addresses=127.0.0.1 -p ${PGPORT} -c unix_socket_directories=/run/postgresql" \
  -l "$ROOT/.pglog" -w start 2>/dev/null \
  || pg_isready -h 127.0.0.1 -p "${PGPORT}" -U postgres >/dev/null 2>&1 \
  || { echo "  ! Postgres failed to start:"; tail -20 "$ROOT/.pglog" 2>/dev/null; exit 1; }

# Wait for TCP to be ready
for i in $(seq 1 30); do
  pg_isready -h 127.0.0.1 -p "${PGPORT}" -U postgres >/dev/null 2>&1 && break
  sleep 1
done

# Create the reputation database if it doesn't exist yet
DB_EXISTS=$($PSQL_ADMIN -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}'" 2>/dev/null || echo "")
if [ "$DB_EXISTS" != "1" ]; then
  echo "  creating database ${DB}…"
  $PSQL_ADMIN -c "CREATE DATABASE ${DB}" >/dev/null
fi

echo "▶ [2/4] Backend deps + schema + demo data…"
if [ ! -d "$ROOT/.venv" ]; then python3 -m venv "$ROOT/.venv"; fi
PY="$ROOT/.venv/bin/python"
"$ROOT/.venv/bin/pip" install --quiet --disable-pip-version-check -r reputation_engine/requirements.txt
export REP_DB_DSN="$DSN"
( cd reputation_engine && "$PY" -m alembic upgrade head )
ROWS=$($PSQL_DB -tAc "SELECT COUNT(*) FROM businesses" 2>/dev/null || echo 0)
if [ "${ROWS:-0}" = "0" ]; then
  echo "  loading demo seed (Team Unstoppable)…"
  $PSQL_DB -q -f reputation_engine/demo/seed_data.sql
else
  echo "  demo data already present (businesses=${ROWS}) — skipping seed."
fi
# demo extras (monitoring keywords + a couple published assets) — idempotent, always applied
$PSQL -d "${DB}" -q -f reputation_engine/demo/demo_extras.sql 2>/dev/null || true

echo "▶ [3/4] Starting API on 127.0.0.1:8000…"
export JWT_SECRET="${JWT_SECRET:-demo-only-secret-change-me-0123456789abcdef0123}"
export ADMIN_SEED_EMAIL="${ADMIN_SEED_EMAIL:-admin@local}"
export ADMIN_SEED_PASSWORD="${ADMIN_SEED_PASSWORD:-DemoAdmin!234}"
export COOKIE_SECURE="${COOKIE_SECURE:-0}"
export COOKIE_SAMESITE="${COOKIE_SAMESITE:-lax}"
export JOB_WORKER=inline
( cd reputation_engine && "$ROOT/.venv/bin/python" -m uvicorn rep_engine.api.main:app --host 127.0.0.1 --port 8000 ) &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null; pg_ctl -D "$PGDATA" stop >/dev/null 2>&1' EXIT INT TERM
for _ in $(seq 1 40); do curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done

echo "▶ [4/4] Building + serving the console on 0.0.0.0:${PORT:-5000}…"
cd "$ROOT/reputation-console"
export NEXT_PUBLIC_API_BASE_URL=/api          # build-time: console fetches same-origin /api/*
export API_PROXY_TARGET=http://127.0.0.1:8000 # runtime: Next proxies /api/* -> the API
if [ ! -d node_modules ]; then npm install; fi
# Always rebuild so NEXT_PUBLIC_API_BASE_URL is baked in correctly
if [ ! -f .next/BUILD_ID ]; then npm run build; fi
echo ""
echo "  ✅ Demo ready. Log in as:  owner@teamunstoppable.com  /  TeamUnstoppable2026!"
echo ""
npm run start -- -p "${PORT:-5000}" -H 0.0.0.0
