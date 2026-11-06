#!/usr/bin/env bash
# Offline simulation: candidate ready; public traffic remains on old revision.
az() {
 case "$*" in
  *properties.configuration.ingress.fqdn*) printf '%s\n' 'example.invalid';;
  *properties.latestReadyRevisionName*) printf '%s\n' 'candidate';;
  *properties.runningState*) printf '%s\n' 'Running';;
  *) printf '%s\n' 'unexpected mock request' >&2; return 9;;
 esac
}
curl() { printf '%s\n' '{"release_id":"same-data-release"}'; }
export WAIT_ATTEMPTS=1 WAIT_DELAY_SECONDS=0
source scripts/azure/wait-for-revision.sh mock-group mock-app candidate same-data-release
