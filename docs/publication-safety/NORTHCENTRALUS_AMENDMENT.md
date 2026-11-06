# Stage A North Central US amendment and execution checklist

Prepared 2026-11-06. **Execution decision: NO-GO. Preparation only is authorized.** This amends the East US 2 plan reviewed at `ab1e47c8a16c589ad6149684d8eb27fd91c2804e`. It does not transfer that execution approval to another region. The authoritative resource/test plan is [STAGING_APPROVAL_PLAN.md](STAGING_APPROVAL_PLAN.md); implementation commands are in [the staging README](../../deploy/staging/README.md).

## Read-only regional findings

North Central US is the preferred fallback. No East US 2 quota request will be submitted. Production remains in `rg-metrik-beta-eus2` / `cae-metrik-beta`, East US 2. The original preflight stopped before Azure mutations at East US 2's managed-environment count 1 used / 1 allowed; this was an infrastructure blocker, not a failed rollout test. All real Stage A cases remain **NOT EXECUTED**, not passed.

| Check | Observed result | Execution implication |
| --- | --- | --- |
| North Central US managed environments, 2026-11-06 10:51 UTC | 0 used / 1 allowed | One environment slot; recheck immediately before approved bootstrap |
| Subscription | Enabled Azure for Students; spending limit On | No upgrade, provider registration or paid fallback authorized |
| Allowed-location policy | North Central US explicitly allowed | No region-policy change required |
| Microsoft.App, ContainerRegistry, Storage, ManagedIdentity | Registered; required resource types advertise North Central US | Metadata compatibility only, not allocation proof |
| Storage | StorageV2 / Standard_LRS available; no listed SKU restriction | Same Table configuration and costs retained |
| Consumption core quota | Unknown: requires the new environment | Require its own available Consumption cores >=3 before workload allocation; production's quota is forbidden evidence |
| Actual physical allocation capacity | Unknown | Only a separately approved allocation attempt can establish it |
| Janitor and restricted identities | Templates prepared; not installed | Must install and independently verify after approval, before environment/workload allocation |
| North Central US execution approval | Absent | No provisioning or spending |

Sanitized evidence: [northcentralus-preflight-evidence.json](../../deploy/staging/northcentralus-preflight-evidence.json). Raw GET receipts and timestamps are in the integration checkout `.tmp/northcentralus-amendment/`; the prior execution receipt and quota-remediation history remain in `.tmp/stage-a-execution/`. This amendment does not erase the earlier blocked attempt.

Azure distinguishes [regional subscription quota, per-environment core quota and actual capacity](https://learn.microsoft.com/en-us/azure/container-apps/quotas). [Environment-specific quotas require an existing environment](https://learn.microsoft.com/en-us/azure/container-apps/quota-requests). Sandbox Cores, another region's quota and production's Consumption quota cannot establish staging core availability.

## Amended architecture and bindings

Every regional resource uses `northcentralus`: new run-specific resource group, Consumption-only environment, app, Basic ACR, Standard_LRS storage and three distinct user-assigned runtime/deploy/janitor identities. All authorization remains scoped to the exact new group/app/registry/table as appropriate. No production data, identities, permissions, DNS, secrets, registry or environment is reused. Runtime Table Data Contributor remains scoped to the single synthetic `StageSubmissions` table. No architecture redesign, extra paid services or SKU changes are included.

Manifests accept only `northcentralus`. Actual environment bindings must use `<environment-label>.northcentralus.azurecontainerapps.io`; generated review output includes the app and revision-specific expected HTTPS endpoints. Global registry/Table suffixes stay `.azurecr.io` / `.table.core.windows.net`, bound to new staging names. Synthetic images require a North Central US OCI label plus the reviewed source/tree/data identities; old images must be rebuilt and reverified. Never invent live IDs, domains or quota evidence to make preflight pass.

The Table endpoint is publicly reachable over HTTPS, but all Table data operations require authorization. Shared Key and anonymous Blob access are explicitly disabled; TLS 1.2 and HTTPS-only are required. New staging managed-identity access, unauthorized-identity denial, valid Shared Key rejection, anonymous denial and HTTP rejection must all be demonstrated in Azure. Public connectivity is not a private-network guarantee. None of these live denials has been executed.

## Cost and resource limits

Fresh USD Retail Prices API evidence at 10:57 UTC on November 6 confirms the same rates and SKUs as the East US 2 proposal. No free grants or student credits are assumed. API rate evidence and every resource's purpose/price appear in the main plan and evidence JSON.

- Maximum three active replicas, each 1 vCPU / 2 GiB, one replica per revision: $0.324/hour combined.
- Two-hour worst-case estimate: **$0.8323**, rounded to **$0.85**, including a full Basic registry day, bounded Table usage, requests and reserved egress.
- Four-hour estimate: **$1.481**, within the unchanged **$2 planning allowance** and proposed **USD 3 authorization ceiling**.
- Ninety-minute test window; two-hour expiry measured from first resource creation, including bootstrap; four-hour incident deadline. No automatic extension, retry, reprovision, resizing, region or quota change.

No observed staging charges exist; no resources were created. Azure billing is delayed, and a budget is not a real-time hard cap. Bounded resources, explicit deadlines, independent cleanup and owner fallback remain necessary. Taxes/currency conversion must fit the spending scope before approval execution. Updated rates beyond policy tolerance or different SKUs require a revised proposal, not silent substitution.

## Exact GO / NO-GO checklist

Each unchecked item is a stop gate at the indicated phase. A successful offline test does not satisfy a live prerequisite.

### Amendment review, before requesting execution approval

- [x] North Central US regional policy, quota, providers, storage SKU and pricing read-only receipts recorded.
- [x] Region-locked manifests, resource locations, endpoint bindings, image-region labels and staging-environment-specific core evidence implemented.
- [x] Existing fixed resource limits, public HTTPS/RBAC-only Table configuration, scoped permissions, recovery matrix and exact-group cleanup retained.
- [x] Offline validation: 1,114 passed / 51 skipped / 3 warnings (full suite, real local Azurite enabled); focused staging/controller/identity suite 131 passed. Ruff lint/format, actionlint (active and inactive templates), frozen lock and installed dependency checks passed.
- [ ] Exact-commit hosted CI, including real synthetic Docker build and browser/PostgreSQL cases, must pass before execution approval.
- [x] Production baseline captured; final comparison required before reporting preparation complete.

### Owner approval: required before any Azure installation or creation

- [ ] Approve the **new full reviewed commit SHA** and this North Central US amendment; prior East US 2 approval is insufficient.
- [ ] Explicitly authorize one bounded North Central US Stage A run, at most **USD 3 incremental spend**, same subscription/SKUs/limits and synthetic data only.
- [ ] Explicitly authorize the narrow default-branch janitor installation and exact-group identity/RBAC/federation bootstrap; do not merge PR #20 or enable production writers to install it.
- [ ] Include creation of only the new Consumption environment as a capacity-check bootstrap after verified cleanup, with immediate owned cleanup if allocation/core checks fail. No paid workload before that gate.
- [ ] Name the operator/fallback cleanup owner, approved runner IPv4 /32, immutable tooling/image/manifest identities and first-resource expiry. Review protected staging gates and exclusive concurrency window.

Approval must cover these concrete actions together or explicitly identify a narrower scope. Nothing in this document sets approval flags or authorizes execution itself.

### Live bootstrap gates after approval, before registry/storage/app allocation

- [ ] Recheck allowed regions, environment slot, provider status, subscription restrictions, current prices and production fingerprints. Stop on drift or material cost changes.
- [ ] Create only the exact approved new group and distinct staging identities/roles/federation; verify no inherited or direct production access. Do not change production policies or principals.
- [ ] Install the separately reviewed default-branch janitor, exact group-only deletion role and immutable manifest/tooling pins. Prove independent `verify_only` success and active 15-minute schedule; retain fallback authority.
- [ ] Create only the new Consumption environment, logging `none`, no dedicated profile. Verify actual North Central US location and its own available Consumption cores >=3. On failure, delete bootstrap and stop; no retry/upsize/quota request.
- [ ] Bind actual new IDs/domain, review exact manifest hash and positive/negative identity scopes. Revalidate source/image provenance, app ingress IP restrictions and default-off approval gates before enabling only the approved staging window.

### Real Stage A acceptance and cleanup: all mandatory

- [ ] Real A/B revisions; explicit A70/B30 baseline; actual readiness, source/image/release/cache/worker identity and read APIs.
- [ ] Real zero-traffic C validation; original A70/B30 retained until explicit promotion.
- [ ] Authorized Table access and each unauthorized identity / valid Shared Key / anonymous / HTTP denial; actual TLS/configuration and RBAC scope readback.
- [ ] C100 promotion and exact A70/B30 rollback with both previous worker identities/configuration; 20 consecutive critical probes and zero unexpected 5xx.
- [ ] Failed candidate/startup and stale fingerprint/gate refusals; owned candidate cleanup without affecting baselines.
- [ ] Foreign-drift refusal with explicit reconciliation; interruption/recovery before and after promotion using durable receipts.
- [ ] Independent expiry janitor plus primary/fallback recovery demonstrated; no dependence on interrupted runner.
- [ ] Whole exact group deleted; all recorded resource IDs, role definitions/assignments, identities/federation and temporary workflow references absent; run flags disabled. ARM verification required, not merely a successful delete command.
- [ ] Production before/after fingerprints, exact revision/image and traffic match; production workflows/gates remain closed. Collect delayed actual costs at 24/48 hours where available.

**Present verdict: NO-GO for Azure execution.** The next executable step is review of the amended exact commit and separate North Central US approval. After approval, execute the bounded bootstrap gates before any workload. All unexecuted real cases remain incomplete; Stage A must not be marked passed.
