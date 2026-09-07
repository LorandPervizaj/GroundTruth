#!/bin/sh
set -e
cd /app
echo "Running database migrations..."
uv run alembic upgrade head
echo "Starting Metrik API..."
export PRODUCT_WRITE_BACKEND="${PRODUCT_WRITE_BACKEND:-database}"
exec uv run groundtruth serve-production --host 0.0.0.0 --port 8000 --workers 1
