#!/usr/bin/env bash
# Weekly crawl: all sources → ETL → analytics refresh (Linux/macOS).
#
# Run manually:
#   ./scripts/run_weekly_crawl.sh
#   ./scripts/run_weekly_crawl.sh --force
#
# Install cron (every Monday 02:00):
#   ./scripts/register_weekly_cron.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="$REPO_ROOT/reports/generated/weekly"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_crawl.log"
PID_FILE="$LOG_DIR/weekly_crawl.pid"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Weekly crawl already running (PID $OLD_PID). Log: $LOG_FILE" >&2
    exit 1
  fi
fi

GROUNDTRUTH="${GROUNDTRUTH:-$REPO_ROOT/.venv/bin/groundtruth}"
if [[ ! -x "$GROUNDTRUTH" ]]; then
  GROUNDTRUTH="uv run groundtruth"
fi

ARGS=(crawl weekly)
for arg in "$@"; do
  ARGS+=("$arg")
done

log "starting weekly crawl: ${ARGS[*]}"
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

if [[ "$GROUNDTRUTH" == "uv run groundtruth" ]]; then
  uv run groundtruth "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
else
  "$GROUNDTRUTH" "${ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
fi

# Refresh static homepage trust snapshot after successful crawl/update.
if [[ "$GROUNDTRUTH" == "uv run groundtruth" ]]; then
  uv run python scripts/update_home_trust_snapshot.py 2>&1 | tee -a "$LOG_FILE"
else
  "$REPO_ROOT/.venv/bin/python" scripts/update_home_trust_snapshot.py 2>&1 | tee -a "$LOG_FILE"
fi

log "weekly crawl finished exit=$?"
