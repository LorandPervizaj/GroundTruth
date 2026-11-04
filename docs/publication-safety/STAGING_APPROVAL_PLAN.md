# Temporary Azure staging — approval proposal

Prepared 2026-11-04. **PLAN ONLY: no provisioning, paid-service activation, production revision creation, or traffic changes are authorized.**

## Decision requested

Approve one synthetic-data Stage A run in the existing Azure for Students subscription `c73c2fd1-9b7f-4221-a868-757128f2e416`, East US 2, with a **USD 3 incremental spending authorization**, a two-hour resource lifetime target, and a four-hour incident/cleanup deadline. Expected cost is about **USD 0.85 or less** before tax; four-hour conservative planning allowance is **USD 2**. No automatic retries or extensions beyond this authorization. If region, SKU, capacity, required services, or quoted rates change materially, return for approval before provisioning.

Approval covers only the resources and Stage A tests below, including deleting those exact temporary resources. Production Stage B and Stage C each remain separately unapproved. A staging pass does not authorize publishing listings, creating a production revision, changing production secrets/configuration, or promoting production traffic.

## Architecture and isolation

Use a new resource group `rg-metrik-stage-<run-id>` containing a new Consumption-only Container Apps environment, one staging app in Multiple revision mode, a new Standard LRS storage account, a Basic image registry, and two new managed identities. Names include a random run suffix; record exact ARM IDs in a run manifest before mutations.

```text
Protected manual staging workflow / local approved bootstrap
  -> new staging deploy identity (staging scopes only)
  -> new Basic ACR (digest-pinned synthetic test image)
  -> new Consumption environment / staging app
       -> revision A: synthetic baseline
       -> revision B: compatible synthetic candidate
       -> revision F: deliberately failing candidate, tested separately
       -> per-revision PostgreSQL sidecar + EmptyDir cache
       -> fresh staging Table account (synthetic records only)

Independent cleanup workflow -> exact staging resource group deletion
```

No references to production environment, registry, Table account, database, Cosmos account, volumes, identities, secrets, DNS names, or artifact URLs are permitted. Build staging images locally from an approved source commit with a generated synthetic release; do not copy the production image because it can contain real listing artifacts. Inspect the build context and final image manifest for data provenance before upload. No GitHub public listing release is created.

Generate fresh ops token, PostgreSQL password, and any storage credentials in memory; use encrypted staging-scoped secret storage, never production secrets. Runtime identity has Table data access only on the new staging account and AcrPull only on the new registry. Deployment identity has Container Apps management only on the new staging app after bootstrap and AcrPush only on the staging registry. Bootstrap and cleanup permissions are separate, restricted to the exact temporary resource group; no standing subscription-wide GitHub writer. All identities and federation records are new, contained in the staging resource group and removed with it.

Storage networking: HTTPS only, disable anonymous blob access, restrict the Table endpoint to the approved runner/staging egress IP allowlist where supported, and verify connections before tests. No VNet, NAT Gateway, private endpoint, or dedicated workload profile is included. App ingress is restricted to the approved runner IP, using the staging app and revision-specific endpoints; fail closed if that rule prevents required revision access. The subscription is shared, so this is resource/data/credential isolation, not a separate subscription security boundary.

## Resources and cost estimate

USD retail rates retrieved 2026-11-04 from Microsoft's Retail Prices API for `eastus2`. Do not assume free grants or student credit remain available. All compute is costed at active rates, including cold starts and failed revisions.

| Required resource | Purpose and limit | Estimated hourly cost | Two-hour allowance |
| --- | --- | ---: | ---: |
| Resource group | Exact cleanup boundary, owner/run/expiry tags | $0 | $0 |
| Consumption-only managed environment | Separate staging control plane, logging destination `none` | $0 base with listed paid features disabled | $0 |
| One Container App, at most three active revisions | Each revision max one replica; total API + cache sidecar allocation **1 vCPU / 2 GiB per replica** | $0.108 each; **$0.324 maximum combined** | **$0.648 maximum** |
| PostgreSQL cache sidecars + EmptyDir | Included within each revision's 1 vCPU / 2 GiB allocation; no managed database/disk | Included above | $0 extra |
| Basic ACR | Isolated image storage, local build, no ACR Tasks; keep images below included storage | $0.00694 equivalent | Reserve **$0.1666**, a full day conservatively |
| Standard LRS storage account / Table service | At most 0.1 GB synthetic records and 100,000 total transactions | Capacity about $0.0000062; transactions metered separately | Under **$0.004** including transactions |
| Two user-assigned identities, federation and scoped RBAC | Separate runtime/deployment credentials; bootstrap and janitor use narrowly scoped approved credentials | $0 resource charge | $0 |
| HTTPS ingress, managed app FQDN and platform TLS | No custom domain, Front Door, gateway or paid certificate | Included; request/egress allowance below | $0 fixed |
| Requests | At most 10,000 external requests; $0.40 per million | Workload dependent | **$0.004** |
| Internet data transfer | At most 0.1 GB responses/evidence; reserve $0.10/GB without relying on free grants | Workload dependent | **$0.01** |
| Cleanup and test runner | Standard GitHub-hosted Linux runner in public repository, no paid runner or Azure scheduler | $0 incremental under standard public-repository allowance | $0 |
| Local evidence / live log streaming | Sanitized records saved outside Azure; no Log Analytics workspace or diagnostic sink | $0 Azure ingestion | $0 |

Compute formula: `(1 × $0.000024 + 2 × $0.000003) × 3600 = $0.108/replica-hour`. Three concurrent replicas for two hours cost $0.648. Adding a full registry day, Table transactions, requests and egress gives approximately **$0.8332**, rounded up to **$0.85**. Four hours at the same compute ceiling gives approximately **$1.49**, rounded up to a **$2 planning allowance**. Proposed **$3 authorization** reserves additional cleanup/failure margin; taxes and billing-currency conversion are excluded and must fit the approved payment limit before starting.

Standard LRS Tables: $0.045/GB-month and $0.00036/10,000 operations. Month conversion uses 730 hours for planning. Registry Basic: $0.1666/day. Newly listed environment management/private endpoint/planned-maintenance meters and dedicated profiles are excluded; inspect the chosen configuration and abandon setup if any becomes required. No Log Analytics, Azure Database for PostgreSQL, VM, paid monitoring, NAT, VNet, backup service, or Azure Automation account is proposed.

The Container Apps monthly grants are shared across the subscription; any remaining free usage reduces actual cost, but is **not** counted in the estimate. Azure budgets and cost reporting are delayed and do not impose a hard real-time spending cap. The $3 figure is an operator authorization ceiling, not a billing guarantee. Resource bounds, timeouts and independent cleanup provide enforcement; if deletion fails, metering can continue and must be reported immediately. If a guaranteed provider-enforced $3 maximum is required, do not provision this design.

Pricing evidence is retained privately at `.tmp/publication-operations-20261104/pricing-eastus2-usd.json` in the main checkout. Re-query the exact meters immediately before an approved run and record account currency, subscription status, quota, provider-registration state and any credit/spending restrictions. No provider registrations or paid fallback SKUs without approval.

Sources: [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices), [Container Apps billing and subscription-wide grants](https://learn.microsoft.com/en-us/azure/container-apps/billing), [logging without persistent storage](https://learn.microsoft.com/en-us/azure/container-apps/log-options), [Table pricing](https://azure.microsoft.com/en-us/pricing/details/storage/tables/), [registry pricing](https://azure.microsoft.com/en-us/pricing/details/container-registry/).

## Preconditions before any approved provisioning

1. Owner approves this plan, spending ceiling and Stage A only in writing. Record operator and one exact run identifier, approved source/tree/image identities, start time and expiration in the manifest.
2. Capture read-only production app/revision/traffic, backend, image/release/cache-guard identities and configuration fingerprints. Baseline mismatch stops the run. Production remains untouched throughout.
3. Prepare and review a staging-specific policy and execution wrapper using the existing controller; **do not edit `deploy/production-policy.json`**. Set exact staging ARM IDs, image registry, synthetic release IDs, cache expectations and per-run guard hashes. Reject any production ID/endpoint/secret reference before Azure calls. Do not weaken production policy to accommodate staging.
4. Review a synthetic fixture builder: small deterministic listing set with fake addresses/contacts, valid manifest and checksums, known search/stat results, empty submissions state, and no downloaded live/public listing dataset. Inspect startup/cache guard and Table backend under the same code paths as production. Ensure 1 vCPU / 2 GiB is sufficient locally; a failed sizing check returns for approval rather than upgrading resources.
5. Create a separate protected GitHub `azure-staging` environment with manual review, branch restriction and default-off gates; never enable `azure-beta` or production gates. Exact OIDC subject is `repo:LorandPervizaj/GroundTruth:environment:azure-staging`. Shared production identity is forbidden. Reuse reviewed controller behavior, with distinct staging resource scope and concurrency lock.
6. Install and verify the independent cleanup schedule **before provisioning**: a separate workflow on the default branch, every 15 minutes, no environment reviewer blocking deletion, no dependency on the test runner. It can delete only the exact approved run resource group using the dedicated scoped janitor permission. A review-branch-only schedule is insufficient. Keep production writer workflows disabled while arranging this prerequisite. If a reviewed default-branch janitor cannot be installed safely, do not provision.
7. Confirm RBAC grants do not inherit production access, network restrictions are supported, no paid features are auto-created, cleanup identity works at the approved scope, and no production/shared resource is an ARM dependency. Owner handles temporary scoped bootstrap authorization; no subscription-wide role grants are proposed.

## Stage A test procedure (real Azure, synthetic data only)

Timebox tests to 90 minutes, reserve 30 minutes for normal cleanup, and record sanitized CLI version, command, exit status, timestamp, ARM response, worker identity and fingerprints for every phase. The operator owns the run and recovery; the independent janitor owns expired-resource removal. Do not count mocked results as Azure validation.

1. **Bootstrap and baseline:** provision only the approved manifest resources. Seed synthetic Table data. Deploy baseline revision A and a second compatible baseline B, both digest-pinned, with a known explicit **70% A / 30% B** traffic map. Record exact revisions/templates/config and direct endpoint identities. Observe both over five minutes; `/health`, readiness, authenticated deployment identity, synthetic release metadata and critical read APIs must all match. Test missing/invalid ops token is denied. No SQL submissions or ordinary contact/submission paths.
2. **Zero-traffic candidate:** keep A/B active and create reviewed candidate C as the third revision with **0% app traffic**. Verify Azure readiness/status parsing, actual revision configuration, immutable image/source/tree/release identity, fresh Table connectivity, cache receipt, and revision-specific endpoint. The public staging FQDN must retain the exact A70/B30 map.
3. **Explicit promotion and rollback:** with A/B/C healthy, explicitly promote staging C to 100%, inspect routing and sample the public staging endpoint until expected identity is observed. Require 20 consecutive critical-read probes with correct identities, zero unexpected 5xx and no readiness failures. Then invoke controller rollback and verify exact restoration of **A70/B30**, including both previous worker identities and configurations. Do not merely compare a release label or use `latestRevision` routing.
4. **Failure handling:** deactivate/remove C after rollback. Use the third slot for F with a bad startup/cache guard or wrong synthetic release identity. Verify it never receives public traffic, controller reports failure, rollback preserves A70/B30, and only its owned failed candidate is cleaned up. Deactivate F before the next scenario. Repeat with a deliberate wrong expected fingerprint; require refusal before mutation. Verify mutation is denied with missing gates, missing exclusive window, missing approval or incomplete identity evidence.
5. **Foreign-change recovery:** use a second authorized staging-only actor to change a harmless, recorded staging configuration/traffic setting between capture and apply. Require detection and refusal to overwrite it. Record the foreign state; the owner explicitly reconciles it against the saved manifest before continuing. Do not claim atomic Azure compare-and-swap protection: the controller uses optimistic readback checks and still needs exclusive operator coordination.
6. **Runner interruption/recovery:** interrupt a staging test after a candidate exists but before promotion; re-enter from the durable receipt and verify original routing remains. Interrupt after staging promotion, then execute the reviewed recovery path from the manifest, verify A70/B30 and worker identities, and preserve evidence. Exercise an expired synthetic run record against the independent janitor, then use that janitor for actual deletion at the end. Cleanup must not depend on the interrupted runner returning.
7. **Final checks:** read production state again and compare to the opening snapshot. Collect staging probes, Table-only evidence and SQL-cache guard receipt, exact promotion/rollback allocations, denial results and cleanup confirmation. A local/mock test, healthy app status, or successful CLI exit alone cannot satisfy these checks.

Abort promotion on any readiness failure, identity/digest/release mismatch, unexpected Table target, cache guard failure, baseline drift, unknown traffic allocation, out-of-scope resource, excessive resource use or deadline breach. Retain last verified staging routing; roll back only when the captured state is still owned and compatible. Otherwise stop writes, capture evidence and require operator reconciliation. Production is never a fallback target.

## Automatic cleanup and deletion verification

- Tag every new resource with `purpose=metrik-stage-a`, `runId`, `owner`, and UTC `expiresAt` (two hours after first resource creation). Tags are inventory aids, not automatic Azure expiry.
- Test workflow has an unconditional `always()` cleanup job independent of test success, using only the manifest's exact subscription and resource-group ARM ID. Validate prefix, run ID and ownership tags before deletion; refuse production/shared IDs. Delete the whole temporary group, including app/revisions, environment, registry/images, storage/data and identities/federation. Never discover deletion targets by broad name matching.
- Independent default-branch janitor runs every 15 minutes and removes the same allowlisted group when expired, using permissions scoped to that group. Delete-capable access does not require a human review that could block emergency cleanup. Verify actual scheduler availability before resource creation. GitHub schedules can be delayed; maintain an owner-controlled fallback deletion command and an escalation deadline.
- Poll group deletion to completion; verify `az group exists` is false and `az resource list --resource-group <exact-group>` yields ResourceGroupNotFound. Cross-check recorded ARM IDs no longer resolve. Verify temporary federation/identities and explicitly scoped role assignments are absent, and staging workflow secret/variable references are removed. Preserve only sanitized evidence outside Azure.
- At two hours the janitor must start cleanup; if the group persists after 30 minutes, notify the operator and run the scoped fallback. At four hours treat any survivor as a cleanup incident, report continuing cost exposure and stop all further tests. No silent extension or reprovisioning.
- Capture production fingerprints and routing again after cleanup; compare without writing production. Recheck cost usage after billing data catches up (next day and again after 48 hours); report actual incremental charges and any discrepancy. Cost data is not proof of deletion; ARM absence is required.

## Known limits and acceptance

Resource/credential isolation still shares subscription quota with production. Check headroom and keep bounded replicas; stop rather than increase quotas. Public Azure service endpoints remain used with IP restriction, HTTPS and synthetic data; private networking would require a new costed proposal. Logs are streamed, so failed-run evidence must be captured by the runner before deletion. Local image build capability, synthetic fixture validation, staging-specific policy and the independent janitor are prerequisites to implement after approval, not completed infrastructure.

Stage A is complete only when real deployment, direct identity, denial cases, promotion, exact weighted rollback, failure/interruption recovery and verified cleanup have receipts, and production snapshots match. Any skipped case is reported as incomplete. Stage B (production zero-traffic candidate) and Stage C (production promotion/rollback) remain separate decisions even after a full staging pass.

Current state: **plan prepared; approval and spending authorization pending; zero staging resources created; Stage A/B/C unexecuted.**
