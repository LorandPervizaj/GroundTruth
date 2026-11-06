# Security patch-up execution plan

Source of truth: the existing local checkout, including uncommitted work. Execution
branch: `security-patch-up`, starting at `a6526772d7778170546cb3facefba72111204a46`.
This document contains implementation guidance only. Detailed findings, credential
locations, resource evidence and test outputs remain in ignored `security/remediation/`.

## Preservation and release gates

Before source edits, an authenticated AES-256-GCM snapshot preserved 6,313 local files
(including tracked artifacts, untracked source, local configuration and private audit
evidence). Every file was decrypted and hash-verified. Its key is protected by Windows
current-user DPAPI: recovery requires this profile's keys; it is not an off-device DR
backup. Installed runtimes/caches and untracked raw data are excluded; exclusions and
Git identity are recorded in the private manifest. Original local changes are never
staged wholesale. Keep the current backend and frontend, especially `web/static/charts.js`.

No push, merge, deployment, production credential rotation, role change, database
write, migration, restart or paid cloud service activation is authorized. The user
approved starting Docker Desktop and an isolated synthetic-data test environment at
`http://127.0.0.1:18765`. Test resources must have unique names, loopback-only ports,
and no application/research volumes or credentials. No active production scans.

## Ordered implementation batches

| Priority | Workstream and areas | Local action | Verification and dependencies |
|---|---|---|---|
| P0 | Database recovery; sidecar and Flexible Server Bicep | Design durable migration, restrict new firewall defaults; never replace live storage | Disposable encrypted dump/restore, schema and row hashes, synthetic writes, restart and rollback; production cutover needs separate approval |
| P0 | Secrets; Git, images, generated artifacts, local config | Redacted exposure classification and permission checks; preserve evidence | Per-occurrence location/provenance, history/image scans; real credential rotation requires owner approval |
| P1 | `src/groundtruth/api/security.py` | Count actual request bytes before handler execution; preserve JSON policy and error contracts | Missing/invalid/understated lengths, multiple chunks, exact boundary, overflow without writes, disconnects, downstream middleware; compare baseline reproduction |
| P1 | Dependencies, `uv.lock`, Docker | Targeted Mako security update; assess each remaining CVE by advisory/version/runtime | Frozen resolution, Windows traversal/control and Alembic render tests; clean image, immutable digest and SBOM; no-fix CVEs remain open |
| P1 | Workflow input and release integrity | Remove shell interpolation of dispatch profile; retain verified release allowlist/hash checks | Execute actual shell with valid events and hostile inputs; artifact tamper rejection tests |
| P1 | Azure posture, `infra/azure/` | Individually reconcile Prowler controls; local IaC changes only | Compile Bicep, inspect effective parameters/resources; paid/owner-dependent actions remain blocked |
| P2 | Source findings, frontend, analytics | Trace each source-to-sink and existing guards; change only established unsafe boundaries | Positive/negative regressions, pinned-rule retest; correctness/style rules are not automatically vulnerabilities |
| Gate | Full application and release verification | Run repeatable QUICK/FULL/RELEASE QA | Exact pass/fail/skip counts; browser journeys, API auth, analytics/ETL, migrations, database recovery, ZAP staging, comparable scanners |

## QA and closure contract

QUICK runs after each patch: candidate diff/forbidden-file checks, redacted secret scan,
targeted Ruff checks, regression tests and relevant scanner rules. Failure blocks that
patch. FULL runs applicable Python, API, ETL, artifact, frontend/bilingual/chart and
browser tests. RELEASE reruns comparable scanner scope, checks clean-image digest/SBOM,
and includes authorized staging dynamic and persistence/recovery tests. Machine-readable
dated outputs link each batch to finding IDs. Missing capabilities are BLOCKED, never PASS.

The private ledger retains every original normalized ID, raw occurrence mapping and
coverage error. Each issue records root cause, affected scope, severity and confidence,
exploitability/impact, strategy, tests, disposition and closure evidence. Allowed outcomes:
confirmed open; needs validation; fixed awaiting QA; fixed independently verified;
evidenced false positive/not applicable; explicitly owner-accepted risk with expiry;
blocked prerequisite; coverage gap. Absence from a later scan alone never closes an issue.

## Database design and rollback

Prefer a separately provisioned durable PostgreSQL service with TLS, restricted app
egress or private connectivity, least-privileged application login, retained encrypted
backups and tested restore. Public-app data and research data stay separate. Removing
an IaC firewall declaration does not remove an existing rule in incremental deployment.
Do not equate an old local restore drill with production recoverability.

Before production cutover: owner-approved inventory and recovery objectives; verified
encrypted production backup; restore to isolated service; schema/migration and row
integrity checks; synthetic application verification; explicit write quiescence and
final sync; planned credential/config switch; monitored validation. Retain the old
database until rollback criteria are satisfied. After new writes, rollback requires
reconciliation, not simply switching connection strings. No data-copy or cutover steps
will run in this local phase.

Rollback local source changes by reverting only the focused security commits; restore
uncommitted original files from the encrypted snapshot into a separate review directory
before copying anything back. Never reset/clean the working tree. Maintain release NO-GO
while unresolved high risks or mandatory verification gaps lack an authorized exception.

## Final handoff

Record branch/commits, complete dispositions and evidence links, per-batch and full QA,
baseline/final comparison with scope differences, residual risks, database safety,
rollback readiness and exact manual approvals. Do not claim all scanner rows are exploits
or all inherited findings are fixed. Keep private evidence outside commits and artifacts.
