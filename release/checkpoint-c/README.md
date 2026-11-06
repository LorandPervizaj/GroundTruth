# Checkpoint C preparation

Scope: combine approved Phase 5/RC `de07127bb222bf977cd63e413cd14e4845322c84`
with reviewed persistence modules from `a30c91aa1133dd1ac85f177781e339d3b06a968d`.
Preserve Phase 5 resolver/parser/market data and preferred frontend bytes.
Production startup additionally rejects every non-Table authoritative write backend.
The original RC dependency lock is retained with only Azure SDK additions.

This directory owns local preparation scripts and ignored `output/` evidence.
Build from a clean Git archive with `build.py`. No push or deployment is performed.
`fixture.py` creates only labeled local synthetic resources; it refuses overwrites.
The Table proxy is a test protocol adapter, **not live Cosmos/managed identity proof**.
It exercises unmodified production-mode runtime SDK requests with verified local TLS
and a synthetic identity endpoint. Live cloud compatibility is independently covered
by Checkpoint B, with the shared persistence implementation retained here.

The fixture's internal Docker network carries Table/identity traffic. A separate
bridge provides Windows loopback access for the browser/test harness. All published
ports bind 127.0.0.1. No production credential or record is used. Disable external
notifications; do not grant cloud permissions or change live firewall configuration.

Checkpoint C production promotion requires separate explicit approval after evidence
is complete. Preserve live Cosmos, backups, current compatible revision and the dirty
original research checkout. Do not rerun migration or geographic research.
