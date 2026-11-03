#!/usr/bin/env bash
# Readiness only. Promotion belongs to safe_deploy.py and requires routing readback.
set -euo pipefail
rg="${1:?resource group required}"
app="${2:?app required}"
revision="${3:?exact revision required}"
if [ -n "${4:-}" ]; then
  echo 'Readiness cannot establish serving release identity; use safe_deploy.py.' >&2
  exit 2
fi
for i in $(seq 1 "${WAIT_ATTEMPTS:-60}"); do
  name=$(az containerapp revision show -g "$rg" -n "$app" --revision "$revision" --query name -o tsv)
  health=$(az containerapp revision show -g "$rg" -n "$app" --revision "$revision" --query properties.healthState -o tsv)
  active=$(az containerapp revision show -g "$rg" -n "$app" --revision "$revision" --query properties.active -o tsv)
  test "$name" = "$revision"
  if [ "$health" = 'Healthy' ] && [ "$active" = 'true' ]; then
    echo "ready_revision=$revision promotion_verified=false"
    exit 0
  fi
  sleep "${WAIT_DELAY_SECONDS:-5}"
done
exit 1
