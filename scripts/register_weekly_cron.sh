#!/usr/bin/env bash
# Register a cron job to run the weekly crawl every Monday at 02:00.
#
#   ./scripts/register_weekly_cron.sh
#
# Remove:
#   crontab -l | grep -v 'run_weekly_crawl.sh' | crontab -

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$REPO_ROOT/scripts/run_weekly_crawl.sh"
chmod +x "$RUNNER"

CRON_LINE="0 2 * * 1 cd $REPO_ROOT && $RUNNER >> $REPO_ROOT/reports/generated/weekly/cron.log 2>&1"

EXISTING="$(crontab -l 2>/dev/null || true)"
if echo "$EXISTING" | grep -Fq "$RUNNER"; then
  echo "Cron entry already exists for run_weekly_crawl.sh"
  crontab -l | grep run_weekly_crawl.sh
  exit 0
fi

{
  echo "$EXISTING"
  echo "$CRON_LINE"
} | crontab -

echo "Registered cron job:"
echo "  $CRON_LINE"
echo ""
echo "Test now: $RUNNER --force"
