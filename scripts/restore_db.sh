#!/usr/bin/env bash
# Restore the reputation Postgres database from a backup_db.sh archive.
# -----------------------------------------------------------------------------
# DANGER: this DROPS the existing public schema in the target DB and replaces it
# with the backup's contents. Usage:
#
#   bash scripts/restore_db.sh backups/reputation-YYYYMMDD-HHMMSS.sql.gz
#
# After restoring an older schema version, bring it current:
#   (cd reputation_engine && set -a && . ./.env && set +a && python -m alembic upgrade head)
#
# Env overrides: REP_PG_CONTAINER, REP_PG_DB
# -----------------------------------------------------------------------------
set -euo pipefail

CONTAINER="${REP_PG_CONTAINER:-rep_pg_test}"
DB="${REP_PG_DB:-reputation}"
FILE="${1:?usage: restore_db.sh <backup.sql.gz>}"

[ -f "$FILE" ] || { echo "no such backup file: $FILE" >&2; exit 1; }

echo "About to restore '$FILE' into database '$DB' on container '$CONTAINER'."
echo "This DROPS the current public schema (all existing data is lost). Ctrl-C now to abort."
sleep 4

# Decompress on the host (supports .sql.gz or plain .sql), pipe into psql in the container.
decompress() { case "$FILE" in *.gz) gunzip -c "$FILE";; *) cat "$FILE";; esac; }

docker exec "$CONTAINER" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"
decompress | docker exec -i "$CONTAINER" psql -U postgres -d "$DB" -v ON_ERROR_STOP=1 >/dev/null

echo "restore complete. Remember to run 'alembic upgrade head' if the backup predates the current schema."
