#!/usr/bin/env bash
# Backup Postgres for Metrik production. Run on the deployment host.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

POSTGRES_USER="${POSTGRES_USER:-groundtruth_app}"
POSTGRES_DB="${POSTGRES_DB:-groundtruth}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"

mkdir -p "$BACKUP_DIR"

DUMP_FILE="$BACKUP_DIR/postgres_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
ARTIFACT_DIR="$BACKUP_DIR/artifacts_${TIMESTAMP}"

echo "Backing up Postgres to $DUMP_FILE ..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl \
  | gzip > "$DUMP_FILE"

echo "Backing up lookup cache and annual report ..."
mkdir -p "$ARTIFACT_DIR"
if [ -d reports/generated/lookup_cache ]; then
  cp -a reports/generated/lookup_cache "$ARTIFACT_DIR/"
fi
if [ -f data/api/annual_report.json ]; then
  mkdir -p "$ARTIFACT_DIR/data/api"
  cp data/api/annual_report.json "$ARTIFACT_DIR/data/api/"
fi

echo "Pruning backups older than ${RETENTION_DAYS} days ..."
find "$BACKUP_DIR" -name 'postgres_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -type d -name 'artifacts_*' -mtime +"$RETENTION_DAYS" -exec rm -rf {} +

echo "Done. Database: $DUMP_FILE"
echo "Artifacts: $ARTIFACT_DIR"
