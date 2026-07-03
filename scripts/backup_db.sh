#!/usr/bin/env bash
# Durable backup of the reputation Postgres database.
# -----------------------------------------------------------------------------
# Writes a timestamped, gzipped pg_dump of the `reputation` DB and prunes backups
# older than KEEP_DAYS. Pairs with docker-compose.db.yml (named-volume container).
#
#   Manual:     bash scripts/backup_db.sh
#   Scheduled:  scripts/install_backup_task.ps1 registers a daily Windows task
#               that runs this via git-bash.
#
# Env overrides: REP_PG_CONTAINER, REP_PG_DB, REP_BACKUP_DIR, REP_BACKUP_KEEP_DAYS
# -----------------------------------------------------------------------------
set -euo pipefail

CONTAINER="${REP_PG_CONTAINER:-rep_pg_test}"
DB="${REP_PG_DB:-reputation}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTDIR="${REP_BACKUP_DIR:-$ROOT/backups}"
KEEP_DAYS="${REP_BACKUP_KEEP_DAYS:-14}"

mkdir -p "$OUTDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUTDIR/reputation-$STAMP.sql.gz"

docker exec "$CONTAINER" pg_dump -U postgres -d "$DB" --no-owner --no-privileges | gzip > "$OUT"

SIZE=$(wc -c < "$OUT")
# Sanity floor: a failed/empty dump must NOT overwrite the rolling set and must not be kept.
if [ "$SIZE" -lt 1000 ]; then
  echo "ERROR: backup suspiciously small ($SIZE bytes) -- removing it, keeping prior backups" >&2
  rm -f "$OUT"
  exit 1
fi

echo "backup -> $OUT ($SIZE bytes)"
# Prune backups older than KEEP_DAYS (never touches anything if the dump above failed).
find "$OUTDIR" -name 'reputation-*.sql.gz' -mtime +"$KEEP_DAYS" -print -delete
