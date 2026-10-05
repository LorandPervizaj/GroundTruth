#!/usr/bin/env bash
# Block until a Container App revision is the latest ready revision (so ingress
# routes to it) and, when a release id is given, /api/meta reports that release.
# `az containerapp update` returns before traffic moves, so checks run right
# after it can still reach the previous revision.
#
#   bash scripts/azure/wait-for-revision.sh <resource-group> <app> <revision> [release-id]
set -euo pipefail

rg="${1:?resource group required}"
app="${2:?container app required}"
revision="${3:?revision name required}"
expected="${4:-}"
attempts="${WAIT_ATTEMPTS:-60}"
delay="${WAIT_DELAY_SECONDS:-10}"

fqdn="$(az containerapp show -g "$rg" -n "$app" --query properties.configuration.ingress.fqdn -o tsv)"
for i in $(seq 1 "$attempts"); do
  ready="$(az containerapp show -g "$rg" -n "$app" --query properties.latestReadyRevisionName -o tsv)"
  state="$(az containerapp revision show -g "$rg" -n "$app" --revision "$revision" --query properties.runningState -o tsv 2>/dev/null || true)"
  echo "attempt=$i latest_ready=$ready revision_state=${state:-unknown}"
  if [ "$state" = "Failed" ]; then
    echo "revision $revision failed to start" >&2
    exit 1
  fi
  if [ "$ready" = "$revision" ]; then
    if [ -z "$expected" ]; then
      exit 0
    fi
    meta="$(curl -fsS -m 30 "https://$fqdn/api/meta" || true)"
    if printf '%s' "$meta" | grep -qF "\"release_id\":\"$expected\""; then
      echo "revision $revision serves release $expected"
      exit 0
    fi
  fi
  sleep "$delay"
done
echo "revision $revision did not become ready${expected:+ serving release $expected}" >&2
exit 1
