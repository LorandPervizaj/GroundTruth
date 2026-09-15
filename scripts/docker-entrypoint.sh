#!/bin/sh
set -e
cd /app

# Prefer a separate migrate job in production (RUN_MIGRATIONS_ON_START=false).
# Default remains true for single-container bootstraps.
if [ "${RUN_MIGRATIONS_ON_START:-true}" = "true" ]; then
  echo "Running database migrations..."
  i=0
  until uv run alembic upgrade head; do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
      echo "Database migrations failed after ${i} attempts" >&2
      exit 1
    fi
    echo "Waiting for database before migrations (attempt ${i}/30)..."
    sleep 2
  done
else
  echo "Skipping migrations (RUN_MIGRATIONS_ON_START=${RUN_MIGRATIONS_ON_START})"
fi

echo "Starting Metrik API..."
export PRODUCT_WRITE_BACKEND="${PRODUCT_WRITE_BACKEND:-database}"
exec uv run groundtruth serve-production --host 0.0.0.0 --port 8000 --workers 1
