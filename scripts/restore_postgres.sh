#!/usr/bin/env bash
# Restore Postgres from a pg_dump backup. DESTRUCTIVE — drops and recreates the database.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup.sql.gz>" >&2
  exit 1
fi

BACKUP_FILE="$1"
POSTGRES_USER="${POSTGRES_USER:-groundtruth_app}"
POSTGRES_DB="${POSTGRES_DB:-groundtruth}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

echo "WARNING: This will drop and recreate database '$POSTGRES_DB'."
read -r -p "Type the database name to confirm: " confirm
if [ "$confirm" != "$POSTGRES_DB" ]; then
  echo "Aborted."
  exit 1
fi

echo "Stopping app container ..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" stop app

echo "Restoring from $BACKUP_FILE ..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();"

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"$POSTGRES_DB\";"

gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "Starting app container ..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" start app

echo "Restore complete. Verify: curl -fsS http://localhost/api/ready"
