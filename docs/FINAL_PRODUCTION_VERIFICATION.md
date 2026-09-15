# Final Production Verification

**Date:** 2026-09-15
**Final status:** **COMPLETE**

## Release

| Field | Value |
|-------|-------|
| source commit | `921510c` (freeze `22b2512` + valuation analytics dedupe fix) |
| image tag | `metrik-api:921510c` |
| image digest | `sha256:d65879dc1d09f21395e3aae2eef73260b11150ca2436ab0c73f828d0b07f79f1` |
| registry | `acrmetrikbetalgy2mu.azurecr.io` |
| prior image (rollback) | `acrmetrikbetalgy2mu.azurecr.io/metrik-api:9ac694d-webui` |
| prior revision | `ca-metrik-api--0000011` |

## Azure

| Field | Value |
|-------|-------|
| resource group | `rg-metrik-beta-eus2` |
| service | Azure Container Apps |
| resource | `ca-metrik-api` |
| FQDN | `https://ca-metrik-api.livelydune-1ec3eb9a.eastus2.azurecontainerapps.io` |
| active revision | `ca-metrik-api--0000013` (Healthy, 100% traffic) |
| postgres | sidecar `postgres:16-alpine` on EmptyDir (not Flexible Server) |
| health probe | `/api/health` |
| readiness probe | `/api/ready` |

## API (production)

| Check | Result |
|-------|--------|
| GET `/api/health` | 200 |
| GET `/api/ready` | 200 |
| GET `/api/markets` | 200 |
| GET `/api/meta` | 200 (corpus 2026-09-07; active_listings 10540) |
| GET `/api/lookup/neighborhood/ulpiana` | 200 |
| POST `/api/valuate` twice | 200 then 200 (after dedupe hotfix) |
| GET `/api/metrics` unauthenticated | 404 (gated) |

## Frontend

All 200: `/`, `/statistics`, `/compare`, `/find`, `/valuate`, `/rent-yield`, `/about`, `/methodology`, `/privacy`, `/terms`, `/market/neighborhood/ulpiana`

## Security

| Check | Result |
|-------|--------|
| metrics protection | PASS (404 without token) |
| valuation PII scan | PASS |
| secrets in git | PASS |

## Recovery

| Check | Result |
|-------|--------|
| previous image recorded | YES |
| rollback available | YES |
| DB backup | EmptyDir sidecar — limited durability (accepted Students beta residual) |

## Notes

1. `scripts/azure/smoke.ps1` expects valuation 503 when disabled; this production app has valuation enabled (200 is correct).
2. Rev `0000012` exposed analytics DuplicateSubmission 500 on repeat valuate; fixed in `921510c` / rev `0000013`.
3. No new Azure infrastructure created.

## Final status

**COMPLETE**
