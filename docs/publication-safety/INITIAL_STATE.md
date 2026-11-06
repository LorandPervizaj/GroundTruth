# Initial state and preservation — November 3, 2026

The requested label `master` did not match the actual checkout. The original checkout is on `codex/minimal-cost-persistence-20261027`, HEAD `eb19c4229fda90d7765d4a477b314f34a96118d9`. It contained 259 modified tracked files and 1989 non-ignored untracked files. A private baseline records SHA-256 for 2248 existing files, status, remote names and ignored-path inventory. It lives outside the remediation tree at `C:/Projects/FartEstate/.tmp/publication-safety-preservation/initial-private.json`; no credentials or record payloads were copied into this report.

Implementation uses the isolated local branch `codex/publication-safety-20261103` in `C:/Projects/FartEstate/.tmp/publication-safety`, based on the actual Table-compatible production runtime `889184ff8a24ac0dacd87433cc71a5405bd23b7b`. The original checkout was never reset, cleaned, switched, staged or committed. Other managed worktrees were inspected only for retained deployment evidence; they were not edited.

## Inventory classification

- Existing source, frontend, workflow and test changes: potentially suitable for Git after their own review; preserved in the original checkout and excluded from this task's commits. Only the previously audited local publication helper was copied into the isolated tree and remediated there.
- Generated lookup cache, reports, API exports, QA results and research captures: retained in place; not blanket-staged. Public artifacts in the baseline serving commit are retained; no new listing artifacts were generated or certified.
- Private security workspace, environment files, credentials, database/backup files and sensitive audit outputs: remain excluded by existing ignore/image policies. Ignored contents were not opened or copied for the Git inventory. Emulator state, downloaded validator/runtime dependencies and detailed test outputs remain under ignored `.tmp/`.
- New task source/tests, a record-free deployment policy and the cache-guard template: explicitly reviewed and suitable for targeted staging. Public resource IDs, Git SHAs and image digests are operational identifiers, not credentials.

## Read-only remote baseline

Remote master remains `0b6f5ce3bc26a1b0313ae7f726e235b64c8f2d52`; its old workflow files match the audited originals. Its configuration accepts only jsonl/database. The local untracked helper was not present on remote master.

Actual production traffic is pinned 100% to `ca-metrik-api--phase5-c-889184ff8a24`, image `acrmetrikbetalgy2mu.azurecr.io/metrik-api@sha256:dbe95c0584a7b914651205fe736a6bd2d45e1b7ee5345ce3737d00055f833d29`. Backend is azure_table, mode Multiple; the sidecar is disposable cache. The live cache guard is revision-bound and must be regenerated without weakening its loopback/database/forbidden-cluster/empty-schema checks. The old PostgreSQL-authority issue was resolved and was not reopened.

The live data release is still the saved October 18 bundle. Pro-RKS recovery and new data certification are independent, out of scope here.

The GitHub azure-beta environment currently has no protection rules/branch policy; repository deployment gate variables are absent, and the required new `METRIK_AZURE_HEALTH_CHECK_TOKEN` environment secret is absent. Names only were inventoried; no secret values were read. These must be configured only after separate authorization. The old remote auto-deploy workflow remains unchanged until an approved push/merge. This local remediation removes push deployment triggers and adds disabled-by-default gates; it does not claim to have changed GitHub settings.
