# Stage A implementation and activation boundary

This directory contains **inactive preparation**, not an installed Azure deployment or janitor. No Azure resource creation, identity/RBAC mutation, paid test, default-branch installation or production change is authorized by this implementation. Production policy is unchanged.

## North Central US amendment, November 6

Staging manifests now accept **only `northcentralus`**. Production stays in East US 2. Reusing an old East US 2 manifest, image label, domain binding or quota receipt fails closed. The earlier East US 2 approval does not authorize this region. See `docs/publication-safety/NORTHCENTRALUS_AMENDMENT.md` for the approval checklist and `northcentralus-preflight-evidence.json` for read-only regional/pricing evidence. Nothing here installs identities or a janitor.

All regional ARM resources derive `location` from the validated manifest. Bind `domain` to the new environment's actual `<environment-label>.northcentralus.azurecontainerapps.io`; no invented endpoint may satisfy live evidence. `render` emits `expected-endpoints.json` for app/A/B/candidate HTTPS origins and the new global Table endpoint. The ACR endpoint remains `<new-registry>.azurecr.io`; its location must be North Central US. Synthetic OCI images carry `io.metrik.staging-region=northcentralus` in addition to source/tree/data labels; rebuild from the newly approved full SHA and verify actual registry manifest digests before running.

## Source and offline verification

- `src/groundtruth/automation/staging.py`: exact subscription/run/resource identities, two-hour expiry/four-hour cleanup deadline, reviewed guard hashes, fixed SKU/compute limits, current-price/permission/janitor evidence validation, atomic durable receipts and scoped cleanup.
- `staging_fixture.py`: deterministic 24-listing dataset in two synthetic neighborhoods with fictional addresses and `.invalid` contacts/URLs, known 6% gross yield, known search results, empty submissions, valid hashed release/QA manifests and deterministic comparables. It never reads corpus data.
- `staging_image.py`: immutable Git-blob allowlist for the build context, fixture/context checksum verification, deterministic release tar, local Docker build, OCI source/data/bundle labels, read-only/network-free inspection of every copied data artifact, and separate baseline/candidate image identities with identical synthetic filesystem layers. It never pushes an image. A config digest is explicitly distinguished from a registry manifest digest.
- `staging_resources.py`: reviewed ARM infrastructure/application templates, secure parameters, scoped role/federation plan. Includes a new environment, ACR Basic, Standard LRS account, Table, three distinct identities (runtime/deploy/janitor), and a run-specific minimal janitor role definition within the temporary group. The third identity makes the separate cleanup credential explicit; it adds no resource charge.
- `staging_storage.py`: HTTPS/TLS/Shared Key/anonymous-access/RBAC validators and future real authorization-denial probes. Public endpoint reachability does not imply public data access.
- `scripts/azure/staging.py`: offline preparation/render/build and separately gated staging inspection, Table health-marker initialization, normalized A/B bootstrap, candidate preparation, explicit promotion, interrupted-run recovery, security probes and cleanup.
- `tests/test_staging.py`: offline negative, fixture, real in-process API, controller and simulated cleanup contracts. These are **not Azure execution evidence**.

The existing `Deployment` controller remains the rollout state machine. Its default production path still promotes only after its existing checks. Opt-in checkpoint callbacks persist staging recovery state before mutation; production receipts do not gain raw configuration. Candidate-only execution leaves routing unchanged; resumed promotion and recovery validate the same deterministic clone, approved baseline and exact worker/routing identity. Rollback refuses foreign drift and restores exact captured weights.

## Approved networking preparation change, November 6

The user approved preparing a **new staging-only, public HTTPS Table endpoint with managed-identity RBAC**. Azure same-region traffic cannot be restricted using the app's public outbound IP allowlist. No VNet/NAT/private endpoint was added; cost and cleanup bounds remain unchanged.

The rendered storage account explicitly sets `allowSharedKeyAccess=false`, `allowBlobPublicAccess=false`, HTTPS-only, minimum TLS 1.2, public network enabled, no trusted-services bypass. Runtime `Storage Table Data Contributor` is scoped to **only `StageSubmissions`**, not the account/group/subscription. The application explicitly selects its new runtime identity through `PRODUCT_TABLE_IDENTITY_CLIENT_ID`. Production principals/client IDs are denied; no production identity is granted a role. Existing subscription-owner administration is a shared-subscription trust boundary, not data-plane access granted by this preparation.

Sources: [Storage firewall limitations](https://learn.microsoft.com/en-us/azure/storage/common/storage-network-security-limitations), [Shared Key prevention](https://learn.microsoft.com/en-us/azure/storage/common/shared-key-authorization-prevent), [Storage security guidance](https://learn.microsoft.com/en-us/azure/storage/common/secure-storage).

After approved provisioning, `storage-security` checks actual account properties and inherited/scoped role assignments, requires an authenticated candidate read through its managed identity, then performs GET-only denial probes for an unauthorized identity, a **valid fresh staging-account Shared Key**, anonymous HTTPS, and HTTP. Wrong status/error codes fail closed. A bad/fabricated key producing a generic signature failure does not pass the Shared Key denial check. The fresh test key is supplied only in process memory through `METRIK_STAGING_TEST_ACCOUNT_KEY`; never print it or use any production key. Collect it only under the separately approved staging bootstrap authority, then discard it. No production key is read or rotated. These real probes remain unexecuted because resources do not exist.

## Offline operator commands

Run from an isolated checkout at the exact reviewed commit with frozen dependencies:

```powershell
$reviewedSha = git rev-parse HEAD
uv sync --all-extras --frozen
uv run python scripts/azure/staging.py fixture --source-sha $reviewedSha --output .tmp/stage-fixture
uv run python scripts/azure/staging.py build-image --output .tmp/stage-fixture
```

Docker must be available for the last command. It builds/inspects local synthetic images only, with no push, Azure call, application startup, or credential requirement. CI runs the same commands on a Linux Docker runner. Do not substitute the production image or existing lookup artifacts.

`prepare` accepts `--run-id YYYYMMDD-xxxxxxxx --source-sha <full-SHA> --image <new-ACR/synthetic@sha256:...> --baseline-image <distinct-new-ACR/synthetic@sha256:...> --sidecar-image docker.io/library/postgres@sha256:... --runner-cidr <one-public-IP/32> --output <run.json>`. It records the actual Git tree and defaults all approvals to false. The run ID derives the exact new resource names. Registry digest values are bound and verified after the separately approved registry/upload step; local config digests must never be substituted.

`render-infrastructure --manifest <run.json> --output <infrastructure.json>` makes no Azure calls. After approved bootstrap readback, `render --manifest <run.json> --bindings <bindings.json> --output <review-directory>` renders the application and authorization/federation plans. Bindings contain only actual new runtime/cleanup client IDs, environment domain, runtime/deploy/janitor principal IDs and the reviewed existing bootstrap administrator's principal ID where inherited owner access exists. They contain no secrets. Review the resulting `bound-manifest.json` and its hash; do not silently edit an approved manifest. The janitor custom role is an ARM resource in the exact new group; do not create an extra subscription-wide role from the review JSON.

The ARM application takes only freshly generated staging `cachePassword` and `opsToken` secure parameters. An authorized future provisioning operator must supply them securely in memory without CLI arguments/logging or committed parameter files. No production secret reuse is supported. Resource creation itself remains a separately approved external operation; this CLI intentionally implements no resource creation mode.

## Preflight evidence contract

`preflight --manifest <bound-manifest.json> --evidence <captured-evidence.json> --output <receipt.json>` requires:

- Explicit spending, provisioning and janitor-installation approvals; same subscription, `region=northcentralus`, registered providers, `quota_environment_id` equal to the exact new manifest environment ID, and numeric `quota_vcpu_available >= 3` from that environment's Consumption usage readback. A regional 0/1 environment count is insufficient.
- Actual default-branch janitor installation, active workflow, a successful independent verification run, 15-minute schedule, and exact manifest hash.
- Verified cleanup permission at only the exact staging group; new distinct runtime/deploy/cleanup principals with no production access; Table permission scoped only to the new table and deployment permission only to the new app.
- A UTC-stamped USD retail quote at most 24 hours old for the exact approved meters. Rate increases beyond 1% or a four-hour estimate above USD 2 fail; the USD 3 authorization is not a real-time provider cap.

Capture actual Azure/GitHub responses for this input; do not populate it from assumptions. Use `az account show`, provider registration readback, Container Apps quota readback, identity and inherited role-assignment readback, `gh api .../contents/.github/workflows/staging-janitor.yml?ref=master`, workflow state and successful run readback, and the Microsoft Retail Prices API. Retain sanitized source responses with the evidence. No current report claims these not-yet-existing staging resources/permissions/installation have passed preflight. The validator intentionally denies absent evidence.

## Independent cleanup installation — separately approved action

`workflows/janitor.yml` and `workflows/primary-cleanup.yml` are outside `.github/workflows`, so neither is active. Do not move them into the default branch or enable variables during this task.

An authorized installation change must:

1. Keep production writers disabled and all production gates/windows closed. Install the reviewed janitor bytes as `.github/workflows/staging-janitor.yml` on master via a narrowly scoped installation review; install the primary reusable cleanup separately. Do not merge the broad integration merely to install cleanup.
2. Approve the zero-cost identity/cleanup bootstrap separately before any paid app/registry/storage allocation. Verify exact target-group ownership and run-specific custom role actions; no production permission, wildcard scope or production OIDC identity is accepted. Bootstrap authority must remain available for fallback if a scheduler, identity or deletion operation fails.
3. Configure only new `METRIK_STAGING_*` variables: run ID, reviewed tooling full SHA, manifest JSON/hash, janitor client ID, tenant/subscription and the default-off janitor/primary-cleanup enable flags. Pin checkout to the reviewed full SHA, never a moving branch. The deploy subject uses `azure-staging`; janitor subjects are restricted to the exact master/integration refs listed in the federation plan. Production `azure-beta` is not used.
4. Dispatch the independent janitor with `verify_only=true`. It checks actual identity, role definition, exact group ownership and manifest without deleting unexpired resources. Capture success and verify a scheduled run is eligible. A feature-branch YAML file or simulated test does not establish installation.
5. Main Stage A must call the primary reusable cleanup under `if: always()` and pass the reviewed manifest/tooling identities. Cleanup must not wait for a reviewer. The independent default-branch job remains responsible for expired resources when the main runner crashes.

The expiry janitor refuses unexpired runs; primary cleanup may remove an owned unexpired run after tests. Both verify exact scope, ownership tags and absence afterward. Permission/transport failures or incomplete deletion are errors, never successful absence. Deletion polling is bounded to ten minutes; workflow timeout is twenty. At two hours cleanup starts; at 2.5 hours the owner uses the scoped fallback, and four-hour survivors are incidents. The shared cleanup concurrency lock prevents overlapping cleanup jobs.

After deletion, independently cross-check recorded ARM IDs, group absence, run-specific role definition/federation/identity absence, and any orphaned authorization objects. Remove staging workflow secret/variable references and disable its run enable flags under the approved installation authority; a deleted janitor identity must not leave a repeatedly failing schedule enabled. Record every remaining item and billable survivor. Recheck delayed billing at 24/48 hours. No cleanup verification is claimed before the real run.

## Bootstrap capacity gate — no execution authorized yet

Azure exposes Consumption core usage per existing managed environment. Before explicit North Central US approval, keep that evidence null/unverified; never copy production's quota. Future approval must include bounded bootstrap: create the exact new group/restricted identities, install and independently verify cleanup at that group, then allocate only the Consumption environment with logging disabled. Before registry/storage/app allocation, read that new environment's core quota and require three available vCPUs. Allocation failure, unreadable quota or fewer than three cores means owned bootstrap deletion and a failed/incomplete run, not retry, quota request, upsizing or migration. No first paid resource is allowed without a verified independent janitor. TTL starts at first resource creation, including bootstrap; do not reset it after binding IDs.

## Future Stage A execution order

Only after the distinct approvals and live prerequisites above: owner provisions the rendered isolated resources, assigns the reviewed scopes, securely supplies fresh parameters, uploads the verified synthetic images and binds their actual immutable registry digests (checking labels, config digest and pulled RepoDigests against the local build). No public GitHub listing release is created.

Then run `initialize-table` to create only the new table's health marker using the staging app's managed identity; it refuses nonempty synthetic submissions or a wrong target. Run `baseline-b` to clone Azure's normalized baseline A template, change only revision suffix/guard, verify both workers, and explicitly initialize A70/B30. It journals before mutation and refuses foreign drift. Both baselines use the same trusted-host set and distinct revision guards; the candidate image differs from the baseline image only in approved image metadata.

Use `inspect` to capture the baseline, then `candidate --approval <immutable-approval.json> --receipt <durable.json>` for zero-traffic candidate/read checks. Run `storage-security` with the unauthorized new janitor credential and valid new-account test key. Run `promote` explicitly, then `recover` to restore exact A70/B30. Each mutating command also requires `--approved-execution`, exact `--manifest-sha256`, captured `--evidence`, and `METRIK_STAGING_EXECUTION_ENABLED=true`; source/tree and protected production-compatibility files are verified. Candidate/promotion/recovery reuse the existing controller, not shell routing logic.

Exercise candidate readiness failure/deactivation through a second staging-only actor, stale expected fingerprints, missing approvals/gates, foreign changes, and process interruption before/after promotion. The durable receipt exists before the mutation and recovery recognizes only its exact owned state. A foreign state is never overwritten; retain safe routing, escalate, and use the scoped group cleanup when needed. Save sanitized CLI exit codes, worker identities, traffic readbacks and before/after production fingerprints. Follow the full test matrix and cost/cleanup deadlines in `docs/publication-safety/STAGING_APPROVAL_PLAN.md`.

All real Azure cases, identity installation, authorization-denial probes, actual expiry deletion and paid execution remain external approved actions, **not completed tests in this preparation**. Production candidate/promotion stages B/C remain separately unapproved.
