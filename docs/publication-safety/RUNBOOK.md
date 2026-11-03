# Controlled validation and activation runbook

## Boundary

Local code is prepared for controlled validation. Nothing in this document authorizes a push, release, dispatch, Azure write, paid resource, traffic change or new listing publication. Do not run historical release scripts or the retired direct `scripts/azure/deploy.ps1` against production. Do not modify a live cache in place.

## Explicit identities

- DATA_SOURCE_SHA: full immutable research-generation commit, independently recorded in the verified data manifest and release target.
- SERVING_SOURCE_SHA plus serving tree SHA: exact reviewed Table-compatible application checkout; not the data tag or master.
- Tooling SHA/tree and explicit branch/tag ref: exact reviewed workflow/controller. GitHub dispatch takes a branch/tag; the helper resolves it to the reviewed SHA twice, and the workflow compares its running SHA before any build. A moving ref fails closed.
- DATA_RELEASE_ID and bundle SHA-256: exact public artifact bundle; neither latest nor a default release is accepted.
- CANDIDATE_IMAGE_DIGEST: registry-qualified image@sha256. The pushed manifest's config digest must equal the local reviewed build config, and OCI labels bind both Git identities, data release and bundle checksum.
- Approved state fingerprint: current global configuration/identity, full pinned traffic map, actual serving revision templates, and non-authoritative app-template drift monitor.

## Before any remote activation

1. Review the local commits and source tree. Integrate runtime and workflow safety changes together; do not cherry-pick runtime onto old master while retaining its push-trigger deployment. The new Azure beta workflow has no push trigger; the production-image push workflow only builds/scans and has no Azure deployment. No push is performed by this task.
2. Separately authorize GitHub remote operations. Establish environment reviewers/restricted deployment branches. Define repository-level `METRIK_DEPLOY_ENABLED=true` and `METRIK_OPERATOR_WINDOW=exclusive` only for an approved maintenance window; defaults are absent/disabled. Configure the existing production ops token as `METRIK_AZURE_HEALTH_CHECK_TOKEN` through a secure secret flow without logs. No such configuration was executed here.
3. Ensure all writers use the reusable weekly deployment writer and its `metrik-ca-metrik-api-production` concurrency group, cancellation disabled. Direct CLI, portal, historical scripts and other principals must not mutate this app during the window. Use RBAC/operator coordination to enforce that restriction. Fingerprints detect observed drift but Azure CLI operations here are not an atomic ARM compare-and-swap; a read/write race cannot be mathematically eliminated by Actions concurrency.
4. Refresh read-only state using `python scripts/azure/safe_deploy.py inspect --output <private-output.json>`. Review target, actual serving revisions, immutable images and policy. Refresh the policy's reviewed rollback images/release IDs/guard hashes and minimum source after any production change. Do not reuse this report's fingerprint as permanent approval.
5. Freeze an explicit serving SHA/tree and tooling SHA/tree. They must exist on GitHub after the separately approved push. Source must descend from the reviewed live runtime, have no unreviewed files, retain the protected backend/artifact/startup interfaces, and expose authenticated /api/deployment. Any intentional protected-interface change requires a new policy review; it is never silently accepted.
6. Separately certify the new data bundle. Pro-RKS source coverage is not waived by this workflow work. New generation records full commit SHAs. Legacy bundles/tags with abbreviated or serving-target provenance require explicit reconciliation; they are not retagged or silently rewritten.
7. Create a reviewed Approval JSON with serving_sha, serving_tree, tooling_sha, tooling_tree, tooling_ref, data_source_sha, release_id, bundle_sha256 and expected_state. Bind its exact bytes by SHA-256 when calling the local publication helper. All input/source/tooling/current-baseline checks precede release creation. Publishing/dispatch still requires explicit human authorization.

## Controlled production validation after authorization

The workflow checks out tooling and serving source independently by full SHA, verifies source and public-only bundle checksums, installs data only into the build checkout, builds/scans the exact image, and verifies the pushed digest against the build. It rechecks the approved baseline before deployment.

The controller validates every actual baseline worker with revision-bound loopback health/readiness/metadata reads. It clones an actual serving revision, preserves durable endpoint/identity/secrets/sidecars/resources, changes only the approved image, revision-bound cache guard, precise candidate trusted host and provenance variables. Global settings and old traffic must remain unchanged. It never initializes an existing nonempty cache or SQL submission store.

Verify these platform adapter contracts in the approved window: ACA revision-specific FQDN availability, exact normalized template readback from YAML update, selected-revision exec output for baseline probes, and healthy revision status. Unsupported transport/readback fails before promotion; do not bypass it. These were simulated locally, not exercised by mutating Azure.

Candidate validation goes directly to its revision FQDN. Authenticated /api/deployment runs FIRST, binds the exact worker/source/digest/data ID and verifies Table readiness, artifacts and cache guard. Only then do read-only search/markets/compare/lookup/yield/annual/frontend checks run. Authenticated GET search probes suppress synthetic product telemetry; a forged probe cannot do so. Redirects are refused before forwarding the ops token. No contact/feedback/notification/submission POST is used.

Immediately before promotion, read back global state, app-template drift, old routing and the candidate. Explicitly set the intended candidate to 100%, read back actual routing, repeat identity/critical-read checks through public ingress, then verify state again. Do not infer serving traffic from latestReady.

On failure before promotion, old traffic remains pinned. On failure after promotion, restore the exact captured compatible weighted traffic map ONLY if current state still matches this deployment. Verify each previous immutable template/worker/release before and after restoration. Foreign changes or missing evidence refuse mutation and require operator action. A failed owned candidate is deactivated only after old routing is verified and its template still matches; unrelated revisions are never cleaned up.

Successful deployments retain old compatible revisions for rollback; review overlap cost and authorize retirement separately. No new paid tier/service or unconditional resource retirement is implicit.

Retain source approval, state fingerprints, immutable build/registry evidence and deployment receipt. A published bundle or deployment_requested message does not mean verified live success. Confirm live revision, exact release ID, backend readiness and restored/routed identity before reporting completion.

Research workflow is data-only by default. A coupled deploy=true research request deliberately stops before public release; review the generated data independently and use the explicit publication/deployment approval path. This unsupported shortcut is fail-closed, not a hidden default deployment.
