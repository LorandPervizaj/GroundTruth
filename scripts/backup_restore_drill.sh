#!/usr/bin/env bash
# Disposable backup/restore drill — does NOT touch production volumes.
# Requires Docker. Creates a throwaway Postgres, loads a fixture dump, restores,
# and verifies row presence + corruption detection.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${ROOT}/.tmp/backup_restore_drill"
IMAGE="${POSTGRES_IMAGE:-postgres:16-alpine}"
CONTAINER="metrik-backup-drill-$$"
USER_NAME="drill"
PASSWORD="drill_password"
DB_NAME="groundtruth"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

rm -rf "$WORK"
mkdir -p "$WORK"

echo "==> Starting disposable Postgres ($IMAGE)"
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER="$USER_NAME" \
  -e POSTGRES_PASSWORD="$PASSWORD" \
  -e POSTGRES_DB="$DB_NAME" \
  "$IMAGE" >/dev/null

echo "==> Waiting for readiness"
for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U "$USER_NAME" -d "$DB_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U "$USER_NAME" -d "$DB_NAME"

echo "==> Seeding fixture table + row"
docker exec -i "$CONTAINER" psql -U "$USER_NAME" -d "$DB_NAME" <<'SQL'
CREATE TABLE product_submissions_drill (
  id serial PRIMARY KEY,
  kind text NOT NULL,
  payload jsonb NOT NULL
);
INSERT INTO product_submissions_drill (kind, payload)
VALUES ('contact', '{"email":"drill@example.com","message":"restore-me"}');
SQL

DUMP="$WORK/postgres_drill.sql.gz"
echo "==> Creating backup at $DUMP"
docker exec "$CONTAINER" pg_dump -U "$USER_NAME" -d "$DB_NAME" --no-owner --no-acl \
  | gzip > "$DUMP"
test -s "$DUMP"
gzip -t "$DUMP"

echo "==> Dropping data and restoring"
docker exec -i "$CONTAINER" psql -U "$USER_NAME" -d "$DB_NAME" <<'SQL'
DROP TABLE product_submissions_drill;
SQL
gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql -U "$USER_NAME" -d "$DB_NAME" >/dev/null

COUNT="$(docker exec -i "$CONTAINER" psql -U "$USER_NAME" -d "$DB_NAME" -Atc \
  "SELECT count(*) FROM product_submissions_drill WHERE payload->>'email' = 'drill@example.com';")"
test "$COUNT" = "1"
echo "Restore OK — recovered row count=$COUNT"

echo "==> Adversarial: corrupt backup must fail integrity check"
CORRUPT="$WORK/postgres_drill_corrupt.sql.gz"
printf 'not-a-gzip' > "$CORRUPT"
if gzip -t "$CORRUPT" 2>/dev/null; then
  echo "ERROR: corrupt backup unexpectedly passed gzip -t" >&2
  exit 1
fi
echo "Corrupt backup correctly rejected by gzip -t"

echo "BACKUP_RESTORE_DRILL_PASSED"
