# Research infrastructure reconciliation — 2026-09-28

Scope: compare `infra/azure/research.bicep`, the weekly GitHub workflows, and the
live `Azure for Students` subscription before provisioning. Resource group used
by the existing API and bot configuration: `rg-metrik-beta-eus2` (`eastus2`).

## Phase 0 provenance

- Reconciled and pushed `master`: `08d393cc57713de8250936a8751ec09a85485d73`.
- Previous live image: `metrik-api:6815a99`, digest
  `sha256:7fde895e2bafa883ecf38b4bb11e2a4fd26096521fe47fa5e8c37c0045b60ac0`.
- CI, dependency audit, secret scan, production image build, Trivy, Azure OIDC,
  deployment, readiness, and smoke checks passed from reconciled `master`.

## Resource matrix

| Expected resource/capability | Declared | Exists | State |
| --- | --- | --- | --- |
| Existing ACR `acrmetrikbetalgy2mu` | external dependency | yes | EXPECTED |
| Immutable `groundtruth-research:<sha>` image | operator build | no tag found | MISSING |
| Job user-assigned identity `id-groundtruth-research-job` | yes | no | MISSING |
| ACR pull assignment for job identity | yes | no | MISSING |
| PostgreSQL Flexible Server 16 | yes | no | MISSING / BLOCKED |
| Research database `groundtruth` | yes | no | MISSING / BLOCKED |
| PostGIS server configuration | yes | no | MISSING / BLOCKED |
| 14-day database backup retention | yes | no | MISSING / BLOCKED |
| Restricted runtime database role | no | no | DRIFTED FROM REQUIRED DESIGN |
| Storage account | yes | no | MISSING |
| Azure Files `pipeline-state` | yes | no | MISSING |
| Azure Files `verified-releases` | yes | no | MISSING |
| Research Log Analytics workspace | yes | no | MISSING |
| Container Apps environment `cae-groundtruth-research` | yes | no | MISSING |
| Environment storage bindings | yes | no | MISSING |
| Scheduled job `job-groundtruth-weekly` | yes | no | MISSING |
| Monday 03:00 UTC schedule | yes | no live target | MISSING |
| Database secret on job | yes | no | MISSING |
| Telegram notification secrets on job | no | no | DRIFTED FROM PIPELINE CODE |
| Optional SMTP notification settings | no | no | OPTIONAL / UNCONFIGURED |
| Public API identity permission to control job | external | yes | EXISTS |
| GitHub environment `groundtruth-research` | workflow reference | no | MISSING |
| `GROUNDTRUTH_AZURE_RESOURCE_GROUP` | workflow variable | no | MISSING |
| `GROUNDTRUTH_AZURE_JOB_NAME` | workflow variable | no | MISSING |
| `GROUNDTRUTH_STORAGE_ACCOUNT` | deploy workflow variable | no | MISSING |
| `GROUNDTRUTH_RELEASE_SHARE` | deploy workflow variable | no | MISSING |
| GitHub Azure OIDC secrets | workflow reference | repository scope | EXISTS; scope needs review |
| Research logs/diagnostics | environment log destination | no research environment | MISSING |
| Drift detection | no | no | MISSING SAFEGUARD |
| Release freshness alarm | no | no | MISSING SAFEGUARD |
| Post-schedule watchdog | no | no | MISSING SAFEGUARD |

## Template findings

The Bicep template compiles. It has two non-blocking `no-unnecessary-dependson`
warnings. It currently embeds the administrator database credential in the job
connection string and gives the runtime administrator privileges; commissioning
requires a restricted runtime role after migrations. PostgreSQL permits Azure-wide
network access through the `0.0.0.0` firewall rule, so the network boundary is
broader than least privilege. Telegram result notifications cannot work because
the job template does not declare or inject `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`.

## Blocking subscription evidence

`az postgres flexible-server list-skus` returns no Burstable PostgreSQL Flexible
Server SKUs in `eastus2`, `westeurope`, `uksouth`, `westus2`, `canadacentral`, or
`northcentralus` for subscription `Azure for Students`. This matches the prior
project warning that the subscription had no permitted Flexible Server SKU.

Per the architecture gate, the job and storage layer must not be provisioned around
an ephemeral database or the public Metrik sidecar. Phase 2 therefore cannot safely
start in this subscription. Required resolution: use a subscription/region that
permits persistent PostgreSQL Flexible Server, or explicitly approve and design a
different persistent research database architecture before deployment.
