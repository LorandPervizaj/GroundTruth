# Operational handoff — 2026-11-04

## Verified scope and Git integration

Original checkout `C:/Projects/FartEstate` is retained on `codex/minimal-cost-persistence-20261027` at `eb19c4229fda90d7765d4a477b314f34a96118d9`; its dirty files are not integration inputs. Isolated integration worktree is `.tmp/publication-integration`, branch `codex/publication-integration-20261104`.

Remote master baseline: `0b6f5ce3bc26a1b0313ae7f726e235b64c8f2d52`. Local remediation: `92b05c887ec084fff8af718784bcfbe3e423a0a4`, `4e27ebd770a1d48445f63c3ae3ddcece779c76f6`, supplemental `b739a1bbfd29bca4023845b430d795597dde9593`. Merge `a09b3ca7014af67f57d088e2c2a72608b6323347` contains both histories and has the exact same tree as b739; no source conflicts or frontend changes. The branch also carries existing local production-compatible commits since master, including Table support, frozen public artifacts, source-quality and location work. These were preserved rather than discarded. This is a broad integration PR, not only a three-commit patch. Operational commit `ec85c0a503f0c995bff85245c71c2a3ab77f69d7` was pushed to the isolated branch and [draft PR #20](https://github.com/LorandPervizaj/GroundTruth/pull/20) created; master was rechecked unchanged. This report's follow-up commit adds evidence only.

Operational follow-up adds independent repository/environment publication and deployment gates, reviewer protection for the research publication job, and corresponding denial tests. Five pre-existing formatter discrepancies were normalized to meet existing repository-wide CI formatting checks. No architecture refactor or listing release is included.

## GitHub configuration actually changed

- Protected `azure-beta`: required reviewer `LorandPervizaj`, custom deployment branch allowlist containing only `codex/publication-integration-20261104`; master is not allowed.
- Disabled legacy writer workflows `azure-beta-deploy.yml`, `weekly-release-deploy.yml`, and `groundtruth-weekly-local.yml`. `groundtruth-weekly-control.yml` was already disabled. CI, image build/scan, k6 and watchdog remain as observed; no writer was dispatched.
- Repository variables: `METRIK_PUBLICATION_ENABLED=false`, `METRIK_DEPLOY_ENABLED=false`, `METRIK_OPERATOR_WINDOW=closed`.
- Distinct environment variables: `METRIK_ENV_PUBLICATION_ENABLED=false`, `METRIK_ENV_DEPLOY_ENABLED=false`, `METRIK_ENV_OPERATOR_WINDOW=closed`. Distinct names prevent environment values shadowing repository denial gates. Existing Azure resource variables retained.
- Created encrypted environment secret `METRIK_AZURE_HEALTH_CHECK_TOKEN` only after checking it was absent and confirming ownership of the existing live health token. Transferred through memory/stdin; no value printed, committed or stored in evidence. No Azure secret was changed.

Remaining limitation: environment readback reports `can_admins_bypass=true`, and self-review is allowed for the sole owner reviewer. This is not two-person approval or protection from a deliberate repository-admin bypass. Configure a second independent reviewer and administrator-bypass restrictions through a supported interface before claiming those guarantees. No real human approval/deployment job has been executed; local tests cover approval/denial contracts only.

Both new deployment definitions use the same production concurrency scope `metrik-ca-metrik-api-production`, cancellation disabled. Exclusive out-of-band operator coordination is still required: Azure state checks are optimistic, not atomic compare-and-swap. Gate/window changes and workflow re-enablement require an explicitly approved window after the remaining validation.

## Read-only Azure evidence

Subscription `c73c2fd1-9b7f-4221-a868-757128f2e416`; group `rg-metrik-beta-eus2`; environment `cae-metrik-beta`; app `ca-metrik-api`. Actual serving revision `ca-metrik-api--phase5-c-889184ff8a24` receives 100% explicit traffic.

Image: `acrmetrikbetalgy2mu.azurecr.io/metrik-api@sha256:dbe95c0584a7b914651205fe736a6bd2d45e1b7ee5345ce3737d00055f833d29`.

Serving source `889184ff8a24ac0dacd87433cc71a5405bd23b7b`; durable backend `azure_table`; data release `2026-W43-saved-oct18-104743-24f9036dc88f-deps`, data through 2026-10-18, 11,747 active listings. PostgreSQL sidecar is disposable cache on `pgdata` EmptyDir. Existing cache startup guard is pinned in `deploy/production-policy.json`; it was not changed live.

Fresh integrated-controller `inspect` fingerprint: `c09762c637dae8b10f58ab6737cb3255243eb4c22edc6964c1e4554757b1b08b`, matching the earlier baseline, with identical traffic and digest. Private before/after GitHub inventories, ops-secret metadata, price meters and final Azure snapshot are retained outside tracked source in `.tmp/publication-operations-20261104` of the original checkout. Secret values are excluded.

Current shared runtime/OIDC identity `id-metrik-beta-app` has AcrPull/AcrPush/Reader on the production registry, plus Container Apps Contributor and Metrik scrape job operator at the production group. Federated subjects reference the GitHub `azure-beta` environment, both legacy name-based and immutable repository-ID form. This is broader than the intended separated runtime/deployment privilege model. **No Azure RBAC or federation was changed.** Prepare separate narrowly scoped deploy/runtime identities; review ownership and migration before revoking existing roles or touching production.

## Validation and pending approvals

- Actual integrated tree: `pytest tests --ignore=tests/e2e -q --disable-warnings --junitxml=.tmp/integration-regression.xml` → **1,031 passed, 47 skipped, 3 warnings**. Skips include external-service/optional integration cases; no cloud test is inferred from them.
- Focused publication/workflow/controller/interface tests → **86 passed**, zero failures/errors/skips, recorded in `.tmp/operational-gate-tests.xml`.
- Repository-wide Ruff lint passed; formatting passed after normalizing five inherited files. All workflow definitions pass actionlint 1.7.7. `git diff --check` passed.
- Gitleaks redacted scan `origin/master..HEAD` before final operational commit scanned 29 commits / 2.72 MB with no leaks. Scan new staged changes before committing/pushing as well.
- Remote CI at ec85c0a: dependency audit **failed**, reporting 36 advisories across aiohttp 3.14.3, black 26.5.1, filelock 3.29.1, msgpack 1.2.2, twisted 26.4.0 and virtualenv 21.14.2. Remote Linux/PostgreSQL tests passed: **1,068 passed, 20 skipped, 3 warnings**; parser gate separately passed 28 tests. The test job then failed installing Chromium because pinned Playwright 1.60.0 does not support the ubuntu26.04 image selected by ubuntu-latest; browser smoke did not run. Performance was still running when recorded. These reports were not independently security-triaged, suppressed or fixed. Dependency remediation and a clean remote rerun are required before readiness; do not infer success from local tests. Staged scan at ec85c0a also passed, and 2,248 original file hashes were rechecked unchanged.
- Prior remediation's real local Table emulator evidence remains documented in REPORT.md; it is not Azure staging validation. No real Azure candidate, promotion or rollback has been performed in this operational run.

See [STAGING_APPROVAL_PLAN.md](STAGING_APPROVAL_PLAN.md) for concrete isolated resources, synthetic fixtures, costs, real promotion/rollback/failure tests, cleanup and spending approval. User explicitly requested plan review before any provisioning. Proposed authorization: USD 3, target two hours, cleanup incident deadline four hours. No staging resource has been created.

## Status and recovery

- **Task 1: PARTIAL.** Merge, local validation, safe branch push and draft PR completed; remote dependency audit failed and remaining remote checks require review. No master merge or deployment permitted.
- **Task 2: PARTIAL.** Read-only baseline verified and staging proposal prepared. Stage A awaits plan/spending approval; production B/C remain separately unapproved. There is no real cloud rollback receipt yet.
- **Task 3: PARTIAL.** Required reviewer, branch restriction, off gates, disabled writers, secure ops secret and concurrency definitions configured/verified. Least-privilege identity migration, admin-bypass policy and real approval-path validation remain open.

Emergency shutdown: leave all repository and environment gates false, operator windows closed, and writer workflows disabled. Cancel any unapproved pending writer before enabling nothing further. For an approved future deployment, capture exact previous revision identities and weighted routing, recover only owned state through the reviewed controller, and refuse to overwrite foreign drift. Current production requires no recovery because this task has made no Azure mutations. Never use generic redeploy scripts or `latestRevision` routing as rollback.
