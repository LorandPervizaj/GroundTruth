"""Produce the focused, evidence-backed RC decision; never promote production."""
from pathlib import Path
import json,hashlib,subprocess,collections,tarfile,xml.etree.ElementTree as ET,datetime
O=Path('C:/Projects/FartEstate');R=Path('C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate');P=O/'release/readiness';E=P/'evidence'
def read(name):return json.loads((E/name).read_text(encoding='utf-8-sig'))
def write(name,value):(E/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
identity=read('release-identity.json');image=read('image-inspection.json');pre=read('preflight.json');azure=read('azure-current.json');prod=read('azure-current-image.json');reg=read('regression-summary.json');api=read('qa-api.json');browser=read('browser-journeys.json');recovery=read('recovery-qa.json');rollback=read('rollback-qa.json')
assert identity['image_manifest_digest']==image['image_digest']==browser['image_digest']
assert browser['passed']==18 and api['passed']==24
assert recovery['identical_retry_during_outage_status']==503 and recovery['identical_retry_after_recovery_result']=='ok'
tests=ET.parse(E/'tests-final-candidate.xml');suites=tests.findall('.//testsuite');counts={k:sum(int(s.get(k,0))for s in suites)for k in ['tests','failures','errors','skipped']};counts['passed']=counts['tests']-counts['failures']-counts['errors']-counts['skipped'];assert counts['failures']==counts['errors']==0
legacy=ET.parse(E/'browser-suite.xml');ls=legacy.findall('.//testsuite');legacy_counts={k:sum(int(s.get(k,0))for s in ls)for k in ['tests','failures','errors','skipped']}
scan=read('trivy-final.json');v=[v for r in scan.get('Results',[])for v in(r.get('Vulnerabilities')or[])];secrets=sum(len(r.get('Secrets')or[])for r in scan.get('Results',[]));sev=dict(collections.Counter(v['Severity']for v in v));assert not sev.get('CRITICAL') and secrets==0
gitleaks=read('gitleaks-frozen-source.json');sem=read('semgrep.json');zap=read('zap-release/zap.json')
write('security-triage.json',{'image_digest':identity['image_manifest_digest'],'image_severity_counts':sev,'image_secrets':secrets,'gitleaks_frozen_source_candidates':len(gitleaks),'secret_triage':[{'file':x['File'],'line':x['StartLine'],'rule':x['RuleID'],'classification':'non-secret image tag or empty sample token setting; checked against source, no exposed credential'}for x in gitleaks],'semgrep_detections':len(sem['results']),'semgrep_errors':len(sem.get('errors',[])),'semgrep_triage':{'property_checks':'Settings.is_development is an actual @property, not an uncalled method.','SQL':'Values are bound parameters; interpolated column identifiers derive from a closed entity map; private remediation command is not a public route.','HTML':'Listed substitutions are escaped or static translation strings, not untrusted raw HTML.','tempfile':'File context is closed/flushed before atomic replace.','coverage':'One MerrJep parser syntax coverage error remains; parser/import/normalization regression tests passed.'},'zap_alert_counts':dict(collections.Counter(a.get('risk')for a in zap.get('alerts',[]))),'residuals':['48 high OS package detections have no fixed version in the scan; local util-linux/system tools, terminal libraries and curl are not user-controlled API execution paths. Non-root UID100; no privileged container or shell execution route established. Not declared fixed or proven exploitable.','Mako CVE-2026-102991 is Windows-specific TemplateLookup drive traversal. Candidate is Linux, public pages are static files and Mako is an Alembic dependency; no attacker-supplied Mako template URI route.','Production HTML contains Google analytics tags intentionally denied by current self-only script CSP. No CSP relaxation. Legacy console assertion fails; critical functionality and runtime-error checks pass.','ZAP medium findings concern inline styles/SRI on CSP-denied third-party scripts; low cross-domain-script findings. No high alerts or demonstrated injection.','Current Azure data-loss risk METRIK-AZ-001 remains a release blocker.'],'full_security_certification':False})
fingerprints={}
with tarfile.open(E/'source-context.tar')as archive:
 for member in archive.getmembers():
  if member.isfile():fingerprints[member.name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
write('frozen-source-fingerprints.json',{'git_sha':identity['git_sha'],'archive_sha256':sha(E/'source-context.tar'),'files':fingerprints})
changed=subprocess.check_output(['git','diff','--name-only','48f5cb6',identity['git_sha']],cwd=R,text=True).splitlines()
original_changes=[p for p,h in pre['source_hashes'].items()if not(O/p).exists()or sha(O/p)!=h]
write('original-checkout-preservation.json',{'original_head_at_preflight':pre['original_head'],'original_branch_at_preflight':pre['original_branch'],'original_head_now':subprocess.check_output(['git','rev-parse','HEAD'],cwd=O,text=True).strip(),'original_branch_now':subprocess.check_output(['git','branch','--show-current'],cwd=O,text=True).strip(),'protected_source_files':len(pre['source_hashes']),'changed_source_files':original_changes,'original_checkout_edits_by_release':'Only new release/readiness evidence package; no reset, restore, stash, clean, branch switch or source staging in original checkout.'})
assert not original_changes
source=identity['git_sha'];digest=identity['image_manifest_digest'];revision=azure['latest_ready_revision'];fqdn=azure['ingress']['fqdn'];rg='rg-metrik-beta-eus2';app='ca-metrik-api'
gates=[('Git freeze','PASS','Clean release source '+source+'; exact Git archive build and preserved original checkout.'),('Regression tests','PASS',f"{counts['passed']} passed; {counts['skipped']} skipped with explicit scope; all 257 recorded recall cases classified."),('Market compatibility','PASS','Current production public bundle retained byte-for-byte; 210 entries and 6,823 comparable rows validated; no historical writes.'),('Persistence/recovery','BLOCKED','Current production pgdata remains EmptyDir with 12 persisted submissions; no verified durable production recovery.'),('Security','BLOCKED','Targeted code/image/API/passive checks completed; known material Azure data-loss risk remains open. Scanner residuals individually classified.'),('Artifact integrity','PASS','Existing official verifier succeeds inside exact image; SHA-256/public schema/privacy and reference version recorded.'),('Image build','PASS',digest),('Staging','PASS','Local production-mode image: 24 API checks, 18 critical browser journeys. Legacy suite 9/10; nonblocking CSP console assertion explicitly retained.'),('Rollback','BLOCKED','Current production digest exists and runs in local QA; safe Azure traffic/data rollback requires durable DB and revision-mode remediation.')]
table='| Gate | Result | Evidence |\n|---|---|---|\n'+'\n'.join('| '+' | '.join(row)+' |'for row in gates)
write('gate-results.json',{'decision':'NO-GO','source_git_sha':source,'image_digest':digest,'tests':counts,'legacy_browser_suite':legacy_counts,'gates':[dict(zip(['gate','status','evidence'],r))for r in gates],'production_changes':False,'historical_writes':False})
test_command="""```powershell
Set-Location 'C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate'
$env:GROUNDTRUTH_TEST_DATABASE_URL='postgresql+psycopg://groundtruth_test:groundtruth_test@127.0.0.1:25439/groundtruth_test'
& .venv/Scripts/python.exe -m pytest tests --ignore=tests/e2e -q -ra --junitxml=C:/Projects/FartEstate/release/readiness/evidence/tests-final-candidate.xml
$env:METRIK_E2E_BASE_URL='http://127.0.0.1:18765'
$env:RUN_E2E='1'
& .venv/Scripts/python.exe -m pytest tests/e2e -q -ra --junitxml=C:/Projects/FartEstate/release/readiness/evidence/browser-suite.xml
```"""
reports={
'RELEASE_CANDIDATE_SUMMARY.md':f'''# NO-GO — release candidate blocked

Runtime source `{source}`, branch `{identity['branch']}`. Local immutable image
`{identity['tag']}` / `{digest}`. No image was pushed and Azure was not changed.

The candidate includes the committed Phase5 resolver and confirmed market model,
the current production public-data bundle and current production frontend. Narrow
repairs cover empty-DB reference sequence bootstrapping, optional Harta imports in
the web CLI, retry honesty after failed product writes, and immutable production
rent-yield reads. Brotli, Certifi and
Pillow locks were updated to fixed versions and verified in the final image.

{table}

Evidence is private under `evidence/`; reports and audit scripts contain no secrets
or listing exports. Read RELEASE_BLOCKERS.md for the smallest safe next action.
''',
'GO_NO_GO_DECISION.md':f'''# NO-GO — RELEASE CANDIDATE BLOCKED

{table}

Production still runs PostgreSQL on replica-scoped EmptyDir. A read-only query
found 12 product submissions: one contact, eleven events. It is not disposable.
The old QA restore does not establish recoverability for those current records.
No new revision, traffic change, DB migration or cloud storage operation is approved
by this decision. The image remains locally available for approval after blockers
are resolved. Do not treat completed software checks as permission to replace the
running replica.
''',
'GIT_AND_SOURCE_MANIFEST.md':f'''# Git and source freeze

Original preflight branch `{pre['original_branch']}`, HEAD `{pre['original_head']}`.
All tracked changes/untracked paths and SHA-256 values are retained in
evidence/preflight.json. Original dirty scraper/research/cache work is preserved.
Release source starts at Phase5 `{pre['phase5_head']}` in an isolated managed
worktree, then focused RC commits. No merge to master, history rewrite or push.

Release branch `{identity['branch']}`; runtime source `{source}`.
Git archive SHA-256 `{identity['archive_sha256']}`.
Full build-source file fingerprints: evidence/frozen-source-fingerprints.json.
Public artifact fingerprints: evidence/image-inspection.json and
public-baseline-freeze.json. Sensitive evidence is ignored, never staged.

Source/config changes after Phase5:

- scripts/load_gazetteers.py: reserve generated IDs above existing/incoming IDs;
  never call setval(0) on a fresh DB.
- src/groundtruth/scrapers/harta_contract.py: defer optional parsel import until
  actual Harta parsing; no crawl or extraction rule changes.
- src/groundtruth/services/product_submissions.py: release the caller's dedupe
  reservation after DB/IO failure, so a retry cannot be reported as a saved duplicate.
- src/groundtruth/api/routes_markets.py: production rent-yield GET serves the
  verified published file instead of rewriting hashed artifacts; missing data503.
- tests/test_published_yield_boundary.py: published-data reads and fail-closed behavior.
- uv.lock: only Brotli 1.2.1, Certifi 2026.10.19, Pillow 13.0.0 package upgrades.
- .dockerignore: exclude audit/research/test/docs/migration developer directories.
- tests/test_release_gazetteer_bootstrap.py, tests/test_web_runtime_imports.py,
  tests/test_product_submissions.py: DB bootstrap, optional-import and retry tests.
- tests/e2e/test_public_site.py: permit an explicitly selected loopback immutable
  QA image instead of silently launching a different development server.
- Fourteen web HTML files align to current production: the old committed Iubenda
  block was absent in the production image. CSS/JS/layout/chart assets unchanged.
- data/api and reports/generated/lookup_cache are copied from the exact current
  production image, not rebuilt from research. Exact paths are recorded in the
  public-baseline-freeze receipt. Artifact bytes are preserved, including CRLF;
  they are not reformatted to silence whitespace warnings and invalidate hashes.
- release/readiness: redacted reports and reproducible audit scripts.

All {len(changed)} changed paths: evidence/release-changed-paths.json.
Evidence-only final documentation may have a later audit commit; it does not change
the frozen runtime/image identity. See evidence/final-git.json for final status.
Rollback of local code is via reviewed reverts on this isolated branch, or simply
leave it unused. Never reset or clean the original dirty checkout.
''',
'REGRESSION_GATE.md':f'''# Resolver regression gate — PASS

The existing Phase5 corpus replay was preserved, not rerun as another geography
study. Runtime reference fingerprint inside final Linux image:
`{image['runtime_reference_fingerprint']}`. Sllovenia resolves as one typed entity
with Aktash/Muhaxhere and Qendra parents inside the image.

The exact 257-observation recall queue (113 frozen pricing primaries) was joined
to original input fields and classified individually. 255 are conservative removals
of inferred Matiqan membership without an explicit Matiqan token; two need stronger
evidence. No confirmed loss of a valid explicit neighborhood was demonstrated.
This classification does not prove that all original property locations were wrong.
Private per-record reasons/hashes: evidence/recall-case-classification.json.

The 6,049 old/new resolver slug differences are hypothetical source-text outcomes,
not historical writes. The separate accepted alias-only fixed-pricing simulation
has zero label moves and zero duplicate-group changes across all 11,730 units.
Equivalent aliases, parent/subarea interpretations and unresolved reassignments
are separated in the preserved Phase5 replay/metric reconciliation.

Dardania: bare name remains neighborhood; explicit school-area variants may resolve
to the school subarea; nearby-school context is not membership. Phase3's 1,854 was a
narrow diagnostic risk flag; Phase5's 2,220 compares old resolver/stored assignments
through the whole frozen corpus. Different definitions, not an unexplained mismatch.

Actual parser, normalizer, references and serialization tests include difficult
aliases, Rruga A/B/C, Ahmet Krasniqi, Qafa, Sllovenia, complex guards, Marigona
identities and source-city provenance. Phase5 pending city/location corrections
remain pending. Four newly demonstrated release defects were repaired and tested.
''',
'TEST_RESULTS.md':f'''# Test results

Frozen final candidate: **{counts['passed']} passed, {counts['skipped']} skipped,
0 failures, 0 errors**. Dedicated migrated/seeded PostGIS DB on loopback port25439;
locked RC environment, no writable research/production DB used. XML and complete
logs: evidence/tests-final-candidate.xml and .log.

The eleven skips: three opt-in historical-price remediation/full-private-restore
tests (historical rewriting is excluded from this rollout); eight Bash/jq watchdog
tests unavailable on this Windows host (private research automation is not changed
or deployed by this public-image release). No public DB integration test is skipped.
The formerly skipped lookup-history test passes after reference seeding.

Legacy browser suite: 9 passed, 1 failed. The failed assertion is console-empty in
the home-counter test: current production CSP rejects existing Google analytics
scripts. The counter assertions passed. This is a recorded nonblocking integration
warning, not a passing test or reason to weaken CSP. Exact XML/log retained.

Critical real-browser journeys: 18/18 on the final image, 9 routes at desktop1440
and mobile375, Albanian/English switches, actual Find/valuation submissions,
compare, charts, yield, navigation and no page overflow. No JS runtime errors.
Repeated automation can trigger expected /api/lang429; raw network receipts retained.
24/24 API checks cover readiness, markets, lookup, search, compare, valuation,
budget matching, validation, writes, private routes, Host checks and headers.

Disposable recovery and rollback results are in STAGING_VALIDATION.md. Initial
uninitialized-DB failures, failed web image, and harness errors are retained, not
overwritten as successes. The harness now uses CSS waits rather than CSP-blocked
string evaluation and waits for PostgreSQL's final TCP listener before restore.

{test_command}
''',
'MARKET_DATA_COMPATIBILITY.md':f'''# Market data compatibility — PASS

No normalized historical rows, eligibility rules or public statistics were rebuilt.
The committed September bundle was older than the running production bundle, so
the release uses only the verified public paths extracted from production image
`{prod['digest']}`. This is preservation of the current public baseline, not
publication of new research outcomes. Production files and final image hashes are
equal byte-for-byte. Official verifier: 210 lookup entries, annual report and rent
yield pass. All 3,728 rent and 3,095 sale comparable rows pass forbidden-field checks.

Published data/corpus timestamps remain those of that bundle (corpus through
2026-10-18); they are not replaced with today's build date. It retains its existing
operator-approved partial source-update metadata. New MerrJep research records are
not silently promoted. Seven market equivalences and typed parents remain in code.

Phase5's actual accepted fixed-eligibility scenarios each have 11,730 units:
4,423 sale / 6,987 rent / 320 other. Alias relabels0; dedup-group changes0; annual
payloads/medians/comparable pools identical. Hypothetical source-text assignments
are not substituted for that accepted compatibility simulation. One Sllovenia
identity can occur in two parent sets, combined as set union:64, not128.
The exploratory551 recoveries and445 city recommendations remain unapproved.
No automatic municipality exclusions, historical migration or new public rollup.
''',
'SECURITY_RELEASE_GATE.md':f'''# Security release gate — BLOCKED by production data-loss risk

Targeted software/privacy controls pass; this is not a full penetration-test claim.
Exact final image scan: {json.dumps(sev)}, secrets={secrets}. No critical detections.
Fixed-version upgrades eliminated the earlier Pillow/Brotli/Certifi detections.
SBOM: evidence/sbom.cdx.json (final digest). Forty-eight high OS package rows have
no fixed version in this scan. No attacker-controlled shell/mount/terminal path is
established; image UID100, not privileged. They remain explicit package risks,
not silently closed and not48 proven remote exploits. Mako's medium Windows drive
traversal does not affect this Linux static-page deployment path.

Gitleaks on the exact frozen source: {len(gitleaks)} candidates, source-reviewed as
two image tags and an empty sample token setting. No usable exposed credential
established. The accidental environment-inclusive scan is retained separately;
its dependency-fixture matches are not release-source findings.

Semgrep: {len(sem['results'])} detections /59 files, one parser coverage error.
Property checks, bound SQL/closed identifiers, escaped/static HTML and file-close
before replace were manually reviewed. See evidence/security-triage.json. The
MerrJep parsing coverage error remains a documented tool limitation; actual tests
pass. Installed tools were reused; no hosted scan or production active scan ran.

Native installed ZAP passive checks completed on exactly nine approved loopback
GET routes, no spider or active production test. No high alerts. Style-inline/SRI
and cross-domain script detections are retained with CSP/actual-source context.
Ops/docs/private paths fail closed; public payload fields, security headers,
untrusted Host, disabled alerts and rate limiting were checked on the image.

Live TRUSTED_HOSTS currently contains '*'; candidate QA uses explicit hosts.
The promotion runbook requires explicit live FQDNs, not wildcard hosts. No exploit
chain is demonstrated from that posture alone. METRIK-AZ-001 is independently
confirmed: public persistent writes remain on EmptyDir, so security/release stays
blocked despite successful software checks.
''',
'AZURE_PERSISTENCE_AND_RECOVERY.md':f'''# Current Azure persistence — BLOCKED

Readback time: {azure['checked_at']}. Resource group `{rg}`, app `{app}`,
environment `cae-metrik-beta`, region East US2. Ready revision `{revision}`;
mode `{azure['revision_mode']}`; latest traffic100%. Exact raw redacted readbacks
are in evidence/azure-current.json and azure-all-revisions.json.

Current metrik-api image `{prod['tag']}` resolves to `{prod['digest']}`. It was
independently pulled by digest and inspected locally. Current PostgreSQL16 sidecar
mounts pgdata at /var/lib/postgresql/data; actual volume storageType is EmptyDir.
An Azure Files storage registration named pgdata exists, but the running app does
NOT mount it as AzureFile. Its existence does not make this volume persistent.
Product write backend=database; migrations-on-start=true in live configuration.

Explicit BEGIN READ ONLY query: 12 product submissions (contact1/events11), no row
contents or secrets collected. A contact submission is durable business state;
the DB is not demonstrably disposable. No verified backup/restore for these
current production records was established. Scoped blob-container and job
inventories returned empty; this is not proof that no off-platform backup exists.
No paid resources, production dumps, DB changes or replica restarts were attempted.

The current disposable QA restore is proven but is not production recoverability.
Smallest safe repair: approve a durable public PostgreSQL target, retention and
controlled cutover; protect current writes, copy only public runtime records,
verify counts/content digests/sequence state and perform independent restore on
disposable storage before changing the revision. Keep research DB separate.
Use approved durable PostgreSQL hosting, not a blind switch to the existing file
share. Existing docs/PUBLIC_DATABASE_DURABILITY_PLAN.md remains the migration basis.
Provider/endpoint/SKU cannot be fabricated; provisioning and cutover require approval.
''',
'IMAGE_BUILD_MANIFEST.md':f'''# Exact image build — PASS

Source `{source}`, branch `{identity['branch']}`; local tag `{identity['tag']}`.
OCI manifest digest `{digest}`. Build-context archive SHA-256
`{identity['archive_sha256']}`. Built from git archive, not the dirty main checkout.
Exact argument array/provenance/base digest: evidence/release-identity.json and
build-metadata.json. Full logs: image-build.log; final-image SBOM sbom.cdx.json.
No remote push, mutable latest tag or historical-tag overwrite occurred.

Image contains /app/web/static/charts.js, /app/src/groundtruth, /app/alembic,
/app/data/gazetteers and verified public data. UID100. No .env/.git/security/
research/release/raw/backups paths in the runtime. Active YAML+typed graph version
`{image['runtime_reference_fingerprint']}`; actual two-parent Sllovenia resolves.
All public artifact hashes match production. Dependency versions:
{json.dumps(image['dependency_versions'])}.

Failed prior candidate evidence retained under attempt1/ and attempt2/. This
manifest refers only to the final tested digest. A local Docker image export is
retained in evidence/candidate-image.tar with its SHA-256 receipt, if export passed.
Documentation-only final evidence commits do not rebuild or rename this image.
''',
'STAGING_VALIDATION.md':f'''# Local production-equivalent QA — PASS for critical journeys

This was loopback Docker QA, NOT Azure staging. Origin127.0.0.1:18765, image
`{digest}`, APP_ENV=production, database-backed writes, verified artifacts,
rate limits enabled, docs disabled, migrations-on-start=false. Only synthetic
disposable data and locally generated test credentials were used.

24 API checks and18 desktop/mobile browser journeys passed. Actual browser
screenshots, runtime/network events, legacy9/10 result and expected CSP denial
are retained; see TEST_RESULTS.md. Production data/artifacts were not regenerated.

Disposable DB dump restored into an independent test DB with equal count/content
fingerprint. During DB outage cached lookup remained200, readiness503 and both
identical contact attempts returned503. After fixture restore readiness returned200;
the identical retry returned200/status=ok and increased the stored count by1.
This verifies the repaired failed-write dedupe path in the actual final image.

The actual current production digest was run against the disposable fixture in
local rollback QA, became ready and served lookup200. The candidate was restored
and became ready again. No Azure revision/traffic rollback was performed. This
does not make an EmptyDir production database recoverable.

Network ingress is bound to loopback; Azure ingress compatibility remains a
promotion-time check after the production persistence blocker is resolved. No
new cloud staging infrastructure was provisioned.
''',
'DEPLOYMENT_RUNBOOK.md':f'''# Production promotion — NOT AUTHORIZED / currently BLOCKED

Do not run scripts/azure/deploy.ps1: it provisions resources and changes secrets/
revision settings. Do not deploy this image while production pgdata is EmptyDir.

Verified identifiers: `{rg}` / `{app}` / `cae-metrik-beta` / East US2;
registry `acrmetrikbetalgy2mu.azurecr.io`. Current FQDN `{fqdn}`.
Candidate source `{source}` and exact tested digest `{digest}` are local only.
Registry push, durable-DB provisioning/cutover, live configuration changes and
traffic promotion each require explicit approval. No registry existence is claimed
for the candidate before its approved push.

1. Approve and implement the controlled durable-public-DB migration described in
   AZURE_PERSISTENCE_AND_RECOVERY.md; verify current records and independent restore.
2. Recheck current ready revision, traffic, digest and storage read-only. Stop if
   they differ from the release evidence. Pin runtime hosts to the verified FQDN;
   retain production guards and use RUN_MIGRATIONS_ON_START=false after reviewed
   schema verification. No historical research migration is included.
3. After approval, push the already tested local image under a new immutable SHA
   tag, record registry digest, and verify it equals `{digest}`. Never rebuild
   after staging or overwrite existing tags; if a digest changes, retest it.
4. After durable-data protection and approval, use multiple revisions and pin100%
   to the old verified revision BEFORE creating the new candidate revision. This
   prevents a latestRevision100% rule from routing traffic prematurely.
5. Check candidate-revision readiness and critical journeys at its approved QA/
   revision endpoint, then promote in bounded steps (e.g.5/25/100%) with explicit
   owner-approved observation windows. Retain the prior revision and data backend.
6. Roll back for readiness503, failed writes, contract/privacy errors, material
   error-rate growth or critical journey failure. Never switch back to an obsolete
   sidecar DB after new durable writes; keep one consistent durable write backend.

CLI syntax verified through installed Azure CLI help, not executed as mutations:

```powershell
az containerapp revision set-mode -n {app} -g {rg} --mode multiple
az containerapp ingress traffic set -n {app} -g {rg} --revision-weight {revision}=100
```

The candidate update requires the approved registry digest and verified durable
configuration. Its exact command must be finalized from that approved target;
inventing an unavailable DB endpoint or claiming an unpushed image exists would be
unsafe. Read-only verification commands were actually executed:

```powershell
az containerapp show -n {app} -g {rg}
az containerapp revision list -n {app} -g {rg} --all
az acr repository show -n acrmetrikbetalgy2mu --image {prod['tag'].split('/')[-1]}
```
Never print raw environment/secret values when reproducing readback; use inspect_rc.py.
''',
'ROLLBACK_RUNBOOK.md':f'''# Rollback readiness — Azure BLOCKED, local image rollback verified

Current observed production target: `{revision}`, digest `{prod['digest']}`,
tag `{prod['tag']}`. The digest exists in ACR and was pulled/run successfully in
local disposable QA. Historical revision0000013 is not assumed to be current.
Full retained revision inventory is in evidence/azure-all-revisions.json.

Current production Single mode plus ephemeral sidecar means replacing/reactivating
a revision can replace its DB state. An image rollback cannot recover lost user
records. There is no honest, verified data-safe Azure rollback under this current
configuration. Do not activate an old revision or restore an old sidecar blindly.

After approved durable-DB protection, common schema verification and multiple-
revision traffic pinning, the application traffic rollback command is:

```powershell
az containerapp ingress traffic set -n {app} -g {rg} --revision-weight {revision}=100
```

This command's syntax is verified, but it was NOT run against production. Recheck
that the named revision remains usable at incident time. Both revisions must use
the same protected durable DB; never fork new writes back into old EmptyDir state.
If storage protection or record reconciliation is uncertain, stop promotion and
preserve the running replica rather than performing a destructive rollback test.

Local QA rehearsal (evidence/rollback-qa.json) stopped only the owned candidate,
ran the current production image against synthetic data, verified ready/lookup,
then restored the exact candidate and verified ready. No migrations were run.
Local source reversal: use isolated-branch reviewed reverts; exact range patch is
retained privately. Original dirty checkout and pre-existing work stay untouched.
''',
'RELEASE_BLOCKERS.md':'''# Minimal material blockers

## RC-01 — Current production persistent state is not protected

Requirement: durable recoverable public product writes before revision replacement.
Verified: current Azure pgdata uses EmptyDir, PRODUCT_WRITE_BACKEND=database; a
read-only query found12 records including one contact. Existing file-share
registration is not mounted. No independent current-production restore is proven.
Smallest safe fix: approve a durable public PostgreSQL target and controlled
write-protected cutover; inventory/export only current public runtime records,
restore and compare count/content/sequence state, prove backup recovery and
restart persistence before moving production traffic. Provisioning, credentials,
storage/network changes and production migration require explicit approval.
Verification: readback shows the durable backend, controlled writes survive replica
replacement, and an independent restore reproduces the protected production state.

## RC-02 — Data-safe Azure promotion/rollback prerequisite

Requirement: candidate/known-good revision can coexist and roll back safely.
Verified: app is Single mode and latestRevision gets100%; restarting old sidecar
revisions does not restore current records. Current image exists and passes local
rollback QA, but that does not protect production data.
Smallest safe fix: after RC-01, approve multiple-revision mode, pin old revision
traffic, preserve a common durable DB and verify readiness/rollback before gradual
promotion. Requires approval for live revision/traffic/configuration changes.
Verification: immutable image identity/readiness, preserved prior revision, common
compatible durable state and authorized non-destructive traffic rollback evidence.

The 257 classified location observations, unapproved historical recoveries/cities,
unconfirmed scanner package detections and optional analytics CSP warnings are not
converted into unrelated manual-adjudication projects. The browser console test
failure remains explicit and nonblocking; CSP is not weakened to silence it.
No production approval is requested while these material blockers remain.
'''}
for name,body in reports.items():(P/name).write_text(body,encoding='utf8')
write('release-changed-paths.json',changed)
write('test-summary.json',counts)
print(json.dumps({'reports':len(reports),'decision':'NO-GO','tests':counts,'image_digest':digest,'original_source_files_unchanged':len(pre['source_hashes'])}))
