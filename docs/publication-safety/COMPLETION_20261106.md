# November 6 technical remediation evidence

Scope: dependency audit, browser/performance CI, executable staging preparation and complete integration provenance. No deployment, Azure provisioning, listing publication, production gate activation, master merge or architectural refactor is included. Final same-head hosted-check results and the readiness decision are recorded in [PR #20](https://github.com/LorandPervizaj/GroundTruth/pull/20) after validation; do not infer hosted success from a local pass.

## 1. Security remediation

Fresh before audit reproduced 36 advisories in six packages. [DEPENDENCY_ADVISORIES_20261106.json](DEPENDENCY_ADVISORIES_20261106.json) records every exact advisory/alias, severity, affected range, patched version, dependency chain, scope, primary source and disposition.

| Package | Before | Final | Dependency scope |
| --- | --- | --- | --- |
| aiohttp | 3.14.3 | 3.14.4 | research â†’ Scrapy |
| Black | 26.5.1 | 26.10.1 | direct dev |
| filelock | 3.29.1 | 4.2.1 | research â†’ tldextract; dev â†’ virtualenv/discovery/CacheControl |
| msgpack | 1.2.2 | 1.2.3 | dev â†’ pip-audit â†’ CacheControl |
| Twisted | 26.4.0 | 26.10.0 stable | research â†’ Scrapy |
| virtualenv | 21.14.2 | 21.14.10 | dev â†’ pre-commit |

Virtualenv also requires packaging 26.3 (previously 26.2). No full-tree upgrade occurred. An intermediate audit exposed another virtualenv advisory, CVE-2026-113713, in 21.14.9; final 21.14.10 fixes it. Audit after the final resolution: **zero known vulnerabilities**, without ignored IDs or changed audit thresholds. `uv lock --check` and frozen synchronization passed. Transitive security floors are constrained in uv while preserving separate install graphs; production `--extra web --no-dev` does not acquire these six research/dev packages. Alternative pip-only installations do not inherit uv constraints and are not the reviewed deployment route.

Package presence is not proof of 36 production exploits. Research HTTP clients process untrusted portal input. The application uses Twisted's Deferred/reactor scheduling, not its IMAP/mail/listener services; Black's affected GitHub Action is absent. Nonetheless all findings were removed through supported upgrades. Stable Twisted 26.10.0 contains the IMAP wildcard escaping fix despite stale patched-version metadata in one advisory. Bounded regex regression, tldextract/file-lock behavior, msgpack/Black/aiohttp interfaces, and usable isolated virtualenv creation are tested. Independent read-only security investigation and candidate review found no concrete surviving route/regression; focused package/scraper/Harta tests passed 85 tests.

## 2. CI recovery

Browser failure: `ubuntu-latest` selected Ubuntu 26.04, unsupported by the locked Playwright 1.60.0 installer. CI now pins Ubuntu 24.04; browser tests run the real isolated application, preserve screenshots, traces and JUnit results, and upload diagnostics even on failure. No production URL is used.

Performance failure: the k6 suite had passed, but background `uv run groundtruth serve` kept uv's cache lock alive until post-job prune timed out with exit code 2. The server now starts through the installed entry point, has an unconditional bounded shutdown step before cache cleanup, and runs on Ubuntu 24.04. No `continue-on-error` or threshold weakening was added. Optional cache pruning remains enabled and must succeed.

Actual repaired hosted evidence at `166fbe6`: [CI run](https://github.com/LorandPervizaj/GroundTruth/actions/runs/42190562075) passed audit, parser gate **28 tests**, PostgreSQL-backed suite **1,071 passed / 20 skipped**, Chromium installation and **10 browser journeys**. [k6 run](https://github.com/LorandPervizaj/GroundTruth/actions/runs/42190561934) passed **1,080/1,080 checks**, **450/450 requests** with zero HTTP failures, artifact upload and uv post-job cleanup. These are intermediate repair evidence, not a claim about a later commit.

The combined final head additionally runs a `staging-image` CI job: synthetic fixture/context generation, Linux Docker build, OCI label verification, network-free/read-only verification of image data contents and distinct baseline/candidate identities. It never logs in to Azure, pushes an image or starts a production application. Local Docker was unavailable, so final hosted evidence is required for this job; a mock is not substituted.

## 3. Staging readiness and safety boundaries

See [deploy/staging/README.md](../../deploy/staging/README.md) for exact files, CLI modes, scopes, bootstrap/federation plans, negative probes, approval gates, independent installation sequence and fallback. Correct relative path from this report is repository root `deploy/staging/README.md`.

Implemented: deterministic synthetic release and expected responses; real in-process critical-read API tests; immutable Git-only build context; digest/label checks; exact per-run policy; fixed resource/price/expiry limits; scoped secure ARM templates; Table health-marker initialization; normalized A/B bootstrap; candidate-only preparation; explicit promotion; durable pre-mutation checkpoints; shared-controller recovery; exact weighted rollback; inactive unconditional/independent cleanup templates; scope/ownership/absence checks; and storage authorization/configuration probes.

The user approved preparing the public HTTPS/RBAC-only staging Table option on November 6. Its endpoint is publicly reachable, but data operations require authorization; Shared Key and anonymous Blob access are explicitly disabled, minimum TLS is 1.2, and runtime Table Data Contributor is scoped only to the new `StageSubmissions` table. No production principal is granted access. Managed-identity, unauthorized-identity, valid Shared Key, anonymous and HTTP probes are implemented for future approved execution; simulated denial tests do not establish actual Azure enforcement.

Final local regression at implementation source `e68ae27`: **1,088 passed, 41 skipped, 3 warnings**. All **47 staging tests** and **11 Table contract/identity tests** passed; Table tests used a real owned loopback Azurite process, including transaction concurrency and process-restart persistence. The emulator was stopped afterward. Skips: 30 PostgreSQL-unavailable cases, 3 opt-in restore drills and 8 Bash/jq prerequisites on Windows. PostgreSQL/browser/performance proof comes from hosted CI and must be checked again on the final head. Full Ruff lint/format, all active workflow actionlint and both inactive cleanup-template actionlint checks passed. Whitespace and staged Gitleaks checks passed before each implementation commit.

Fresh November 6 East US 2 retail quote retained in local `.tmp/remediation-20261106/pricing-current.json`: vCPU $0.000024/second, memory $0.000003/GiB-second, Basic registry $0.1666/day, Standard LRS Tables $0.045/GB-month and $0.00036/10K operations; requests $0.40/million. This preserves the approximately $0.85/two-hour estimate, $2 conservative allowance and proposed $3 authorization. No free grant is assumed; no hard provider spending cap is claimed.

External actions still required: explicit spending/provisioning approval; approved default-branch cleanup installation and its actual independent verification; zero-cost identity/cleanup bootstrap under separate authority; exact scoped RBAC/OIDC/role readback; live quota/fresh-price proof; actual new registry digests/identity/domain bindings; fresh staging-only secrets; and real Stage A deployment, denial, promotion, recovery and cleanup tests. A feature-branch template is not an installed janitor. Production B/C remain separately unapproved. No Azure resources or active cleanup automation were created by this work.

## 4. Git integration and review

Branch: `codex/publication-integration-20261104`; [draft PR #20](https://github.com/LorandPervizaj/GroundTruth/pull/20). Recovery branch at the original integration head: `codex/recovery-publication-20261106` â†’ `8b8f3e9da56620f1a841aa3bc8a3ca38491ce10d`. Remote master remained `0b6f5ce3bc26a1b0313ae7f726e235b64c8f2d52` when refreshed. Original checkout remains `codex/minimal-cost-persistence-20261027` / `eb19c4229fda90d7765d4a477b314f34a96118d9`; its dirty files were not imported.

Implementation commits: `48d0e6f` dependency remediation; `166fbe6` browser/performance fixes; `e68ae27` staging preparation/controller extension and offline tests. Later inventory/report commits are metadata-only. Full final identities are available from PR head and the inventory's explicit snapshot boundary; the inventory cannot embed its own final commit hash without a self-reference.

[INTEGRATION_INVENTORY_20261106.json](INTEGRATION_INVENTORY_20261106.json) is generated by `scripts/review_publication_integration.py`. Every changed file has category, originating commits, historical status, inclusion reason, runtime/data-impact flags, necessity distinction, evidence and master/production/head SHA256. The snapshot is stated explicitly; subsequent self-describing report/inventory updates are metadata-only. No file is accepted in an unexplained category.

At the implementation snapshot there were **429 changed files / 35 commits**, not the old 413-file count. Categories: 218 frozen artifacts, 62 tests/fixtures, 31 location/gazetteer, 29 source-quality/parsing, 26 documentation, 21 publication/deployment safety, 18 other historical research, 16 Table/serving compatibility and 8 CI/tooling. **369 files were byte-identical to actual serving source 889184f.** Added review metadata is counted by the refreshed inventory. All 218 frozen public artifact files match production; no release was regenerated. Preferred frontend, Table implementation, configuration, startup protections and entrypoint also match production byte-for-byte where protected. New controller/staging tooling is explained and tested separately.

One initially uncategorized file, `reports/research/independent_evidence_verification.ipynb`, was investigated: originating commit `2cc30f7`, four cells, aggregate agreement/confidence/date-count outputs, references to private inputs without those inputs. It is preserved historical research evidence, not a new private-data export. Historical scripts are not invoked or treated as newly authorized operations.

Splitting recommendation: keep this draft/history intact and use stacked review boundaries. First review/retain the remote writer barrier; then review the production-compatible prerequisite history through `889184f`; then review the publication/staging delta from that exact baseline. The source guard requires ancestry from 889184f, which includes the durable Table work (`d79924f`/`de07127`) and guarded cache/serving changes (`35bce78`, `3204415`). Cherry-picking only the publication commits onto master would omit those requirements or fail source verification. Earlier research/location/source-quality work is separately identified and is not intrinsically required for publication; it can be reviewed as prerequisite history without dropping it or force-rewriting this PR. No branch/PR split or master merge was performed automatically.

## 5. Operational state and final evidence boundary

Production before-state fingerprint: `c09762c637dae8b10f58ab6737cb3255243eb4c22edc6964c1e4554757b1b08b`. Serving revision `ca-metrik-api--phase5-c-889184ff8a24`, explicit 100% traffic; image digest `sha256:dbe95c0584a7b914651205fe736a6bd2d45e1b7ee5345ce3737d00055f833d29`; backend `azure_table`; unchanged release `2026-W43-saved-oct18-104743-24f9036dc88f-deps`. Final read-only comparison, original-file preservation hashes and remote gates/writer state must be rechecked after hosted validation and recorded in the final PR/body receipt.

Production writer workflows remain disabled, repository/environment publication/deployment gates false, and operator windows closed. Existing owner-review/branch restriction protections remain; administrator bypass and sole-owner self-review limitations were not silently changed. No production OIDC/RBAC/secret rotation occurred.

Status vocabulary for final closure: dependency/workflow implementation and provenance can be RESOLVED only with current evidence; Azure provisioning, live identity/janitor installation and real Stage A are BLOCKED â€” EXTERNAL APPROVAL. Production B/C, new listing publication and architecture refactoring remain DEFERRED â€” OUT OF SCOPE. Any failed final hosted job remains BLOCKED â€” TECHNICAL; this document does not waive it.

## North Central US amendment

The later [North Central US amendment](NORTHCENTRALUS_AMENDMENT.md) supersedes only the staging region and related bindings. East US 2 preflight stopped at 1/1 environment quota before any resources were created. North Central US reports 0/1, but its new environment core quota and actual capacity remain unverified. The original East US 2 execution approval is not North Central US approval. Stage A is NOT EXECUTED; no provisioning, identity/janitor installation, spending or production action is authorized by this amendment. See the amended plan and checklist for exact next approvals and bootstrap gates.
