# Publication and deployment safety remediation

**Recommendation: READY FOR CONTROLLED VALIDATION — local implementation only.** No production publication/deployment was executed. Remote activation is not yet ready: the new commits are local, the protected environment/gate variables/ops-token secret still require separately authorized setup, and the new data bundle has not been certified.

## Outcome and provenance

Runtime/workflow commit: `92b05c887ec084fff8af718784bcfbe3e423a0a4` on `codex/publication-safety-20261103`, based on the actual deployed Table-compatible source `889184ff8a24ac0dacd87433cc71a5405bd23b7b`. The implementation preserves the preferred frontend and all public market artifact bytes from that baseline. No historical, research, SQL or Table records were rewritten by this remediation. The original checkout remains on its original branch/HEAD with its pre-existing work preserved.

The exact test/documentation commit and file lists are recorded in local Git history after this runtime commit. Source/workflow files are committed separately from regression tests and this documentation. The final source-identity verification and preservation receipts are retained under ignored `.tmp/` and in the original checkout's private preservation folder.

## Findings and fixes

| Finding/root cause | Final behavior / primary files |
|---|---|
| Local helper defaulted to incompatible master and tied data tag to serving code | `azure_publication.py` requires exact reviewed Approval bytes/hash, independently verifies serving/tooling commits and trees, production baseline and protected Table/startup/artifact interfaces before release writes; data tag targets DATA_SOURCE_SHA, serving source is a separate input. GitHub branch/tag ref is explicitly resolved and checked against immutable tooling SHA; no master fallback. |
| Ready revision was confused with public routing | `deployment.py` snapshots actual pinned serving allocations/templates; `safe_deploy.py` creates a candidate without changing global routing, validates its exact FQDN, explicitly promotes, and verifies actual routing plus worker identity. `wait-for-revision.sh` is readiness-only and rejects its old shared-ingress identity shortcut. |
| Rollback recreated a latest/template image and ignored routing | Captured actual serving digests, release identities and weighted traffic maps are retained. Previous worker/templates must still match and pass read checks before/after restoration. Foreign drift or unavailable evidence refuses stale mutation. Failed owned candidates are deactivated only after verified old routing; no unrelated revision is removed. |
| Independent workflow writers could race | Azure beta delegates to the one reusable weekly writer and its shared concurrency group, cancellation disabled. Ordinary push no longer deploys. Repository gates and an exclusive operator window are required. Direct legacy deployment script stops before any Azure operation. |
| Images were recorded by digest but deployed by tag | Workflow verifies registry manifest config digest against the reviewed local build, records independent OCI provenance, and passes only registry-qualified image@sha256 to the state machine. Every rollback/sidecar identity must also be an approved digest. |
| HTTP failures and unrelated metadata matches could pass smoke | Every required API/frontend read asserts HTTP and schema; exact parsed release ID and authenticated worker/source/digest/backend/guard identity are required. The identity check runs first; rejected credentials stop before search telemetry. Authenticated read probes suppress only synthetic GET search events; forged probes remain ordinary requests. No production contact/feedback/notification/submission POSTs are issued. |
| Live cache guard was tied to a previous revision | Reviewed template preserves loopback/user/database/forbidden-cluster/empty-schema/head/zero-SQL-submission protections and binds the intended new revision. Old guard command hashes and rollback image identities are policy-pinned. No unconditional migration is added. |
| Abbreviated/unknown research provenance | New weekly generation requires full immutable data-source SHAs; unknown and abbreviated values fail. Old public releases are not rewritten or retagged. |

The app template/latest pointer is never used as authoritative serving identity. It is independently monitored for drift so another operator's non-serving template change also prevents stale promotion/rollback. Global identity/configuration and current routing are re-read before every unsafe step.

## Before / after lifecycle

Before: master/tag checkout → tag image build → create revision → compare latestReady/shared public metadata → log checks → recreate old image after failure. That could regress code, miss the actual traffic allocation, falsely report success on an unchanged release and race another writer.

After: validate explicit data/source/tooling approvals → read current immutable serving identities and state → verify source/public bundle → build/scan/prove immutable digest → verify baseline workers → clone actual serving configuration with a revision-bound cache guard → check unchanged old routing → validate candidate directly with no product writes → recheck drift → explicitly promote → verify exact routed worker/data → retain evidence. Failure restores only the exact compatible captured allocation when ownership still matches.

## Validation evidence

Final combined suite: **239 passed, 3 skipped, 1 warning** in 32.21 seconds. Command (from this worktree, using its locked web/dev virtual environment):

```powershell
$env:PYTHONPATH="$PWD/src"
# The Table emulator connection and restart-script variables point ONLY at the owned 127.0.0.1:27402 fixture.
.venv/Scripts/python.exe -m pytest tests/test_deployment_safety.py tests/test_deployment_interfaces.py tests/test_weekend_publication.py tests/test_automation_workflows.py tests/test_automation_weekly_release.py tests/test_release_verify.py tests/test_release_metadata.py tests/test_release_publication.py tests/test_ready_api.py tests/test_production_cache_startup.py tests/test_production_hardening.py tests/test_release_gazetteer_bootstrap.py tests/test_product_submissions.py tests/test_product_event_logging.py tests/test_table_identity.py tests/test_table_submissions.py tests/test_phase5_locations.py -q --disable-warnings --junitxml=.tmp/final-tests.xml
```

The three skips are unchanged SQL reference-sequence tests because an isolated PostgreSQL test database was not configured. They do not hide Table persistence or deployment tests; those ran. One existing warning is retained. No browser/E2E or new production image scan/deployment is claimed by this local run.

Actual isolated Table checks: **11 passed**, including atomic transactions, concurrent duplicate handling, lost-success replies, record import preservation, managed-identity audience checks, and a real local emulator/process restart with a fresh SDK client and preserved record/dedupe guard. Azurite 3.35.0 ran as a disposable Node process bound only to 127.0.0.1, with synthetic credentials/state under ignored `.tmp/`. Docker fixture creation was rejected by automatic approval review without a detailed reason; the lower-impact process fixture succeeded. Two interrupted Windows captured-pipe test runs were retained as harness history; the file-based bounded restart harness and final run passed. This is emulator persistence, not a new live Azure recovery test.

Actionlint 1.7.7 validated all repository workflows; downloaded archive checksum matched the official release sidecar. Ruff, Bash syntax, PowerShell parsing and git diff checks passed. Gitleaks checked staged intended changes with redaction; no leaks found. Runtime changes were not newer than the final combined suite.

### Original failure coverage

- Incompatible/older master, wrong source/tree, missing backend, removed startup guard, wrong tooling/ref and invalid release target fail before publication.
- Ready candidate with old traffic, same release from a wrong worker, and new data with unchanged routing cannot satisfy promotion.
- All critical HTTP 500s, malformed schemas and expected IDs found only in unrelated fields fail.
- Wrong backend, source, immutable image provenance and startup guard fail.
- Shared writer lock/default-off push policy is validated structurally; state-machine tests reject changed fingerprints, foreign traffic and foreign non-serving template updates.
- Candidate failure keeps old routing. Post-promotion failure, including an unhealthy candidate, restores exact compatible prior routing; weighted 35/65 allocation is covered.
- Azure read/transport failure refuses mutation or explicitly reports unverified recovery; no success is fabricated.
- Original Bash audit scenario is retained under tests/fixtures/publication. Its old exit 0 false success and new exit 2 rejection are in evidence/wait-routing-before.json and evidence/wait-routing-after.json.
- evidence/simulated-lifecycle.json retains successful simulated promotion and exact weighted rollback receipts. All cloud/HTTP operations in these receipts are mocked.

## Privacy, source and Git preservation

See INITIAL_STATE.md and PRESERVATION_CATEGORIES.json. The original 2248 non-ignored file fingerprints were checked unchanged before the runtime commit. Existing generated files, source experiments and private research/security/credential/backup data were not included. No blind staging, destructive reset/clean, frontend replacement or blanket ignore-policy weakening occurred. Local emulator/validator dependencies, full private inventories and detailed test logs are excluded from Git and the production build context.

## Remaining activation requirements and limits

1. Obtain separate approval before any push, release, workflow dispatch, environment/secret change or Azure operation. Local removal of push triggers does not claim to have changed the still-old remote workflows.
2. Configure reviewers/branch restrictions, the new ops-token secret and default-off repository gates securely. None currently exists as required by this new path; no values were exported or changed.
3. Validate the platform adapter against actual ACA revision FQDNs, normalized YAML/template readback and selected-revision exec transport in the authorized controlled window. Unsupported operations fail closed. Local mocks are not a live promotion or rollback test.
4. Enforce an exclusive operator/RBAC window for out-of-band writers. Fingerprints plus Actions concurrency are optimistic drift protection, not a server-side atomic compare-and-swap guarantee. Any observed foreign change requires a fresh plan; the controller does not overwrite it.
5. Re-review source policy and current production fingerprint after any live change; an old policy cannot silently authorize a newer baseline or different rollback image.
6. Independently certify the new listing bundle and resolve or explicitly bound Pro-RKS coverage. This task did not certify/publicize those listings.
7. Approve any replica overlap costs and subsequent retirement. Successful old revisions are retained for compatible rollback; no paid tier/resource creation or retirement is implicit.

Exact future controlled steps and stop conditions are in RUNBOOK.md. Remote activation and listing publication remain unexecuted.
