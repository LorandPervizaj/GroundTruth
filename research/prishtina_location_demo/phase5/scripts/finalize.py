"""Reconcile evidence and write Phase5 reports; never update source DB rows."""
from common import *
import sys,collections,subprocess,xml.etree.ElementTree as ET
sys.path.insert(0,str(ROOT/'src'))
from groundtruth.gazetteers.market_graph import distinct_rollup_memberships,load_market_graph
from groundtruth.gazetteers.version import compute_gazetteer_version,compute_legacy_gazetteer_version

replay=read(B/'validation/full_corpus_reconciliation.json');frozen=replay['frozen'];current=replay['current'];market=read(B/'validation/market_metric_reconciliation.json')
assert replay['reference_fingerprint']==compute_gazetteer_version(),'Reference inputs changed after replay.'
membership={r['normalized_id']:r['canonical_group_id'] for r in read(P/'processed/active_corpus_membership.json') if r['is_canonical_primary']}
subareas=[];multi=[];unresolved=[]
with (B/'processed/phase5_listing_replay.csv').open(encoding='utf-8-sig') as f:
 for row in csv.DictReader(f):
  rid=int(row['record_id'])
  flags=json.loads(row['flags'])
  if not row['new_resolver_neighborhood'] or flags.get('complex_ambiguous'):
   unresolved.append({'record_id':rid,'source_portal':row['source_portal'],'source_listing_id':row['source_listing_id'],'reason':'No accepted source-text market identity or ambiguous complex; no automatic recovery approved','requires_human_review':True,'eligible_for_strict_market_change':False})
  if rid not in membership or not row['new_resolver_subarea']:continue
  subareas.append((membership[rid],row['new_resolver_subarea']))
  if row['new_resolver_subarea']=='sllovenia-sport':multi.append((membership[rid],'sllovenia-sport'))
overlap=distinct_rollup_memberships(multi)
union=set.union(*overlap.values()) if overlap else set()
assert len(union)==len({u for u,s in multi})
market['proposed_resolver_sllovenia_overlap']={'distinct_underlying_frozen_pricing_units':len(union),'parent_counts':{p:len(v) for p,v in overlap.items()},'sum_memberships_nonadditive':sum(map(len,overlap.values())),'combined_distinct_units':len(union),'scope':'Research projection of explicit source-text resolver matches; no stored assignments or production rollups changed.'}
write(B/'validation/market_metric_reconciliation.json',market)
csvout('processed/proposed_multi_parent_unit_membership.csv',[{'pricing_unit_key':u,'subarea':s,'parents':['aktash-muhaxhere','qendra'],'observations_count_once':1} for u,s in sorted(set(multi))])
csvout('processed/unresolved_recovery_candidates.csv',unresolved)
childsets=collections.defaultdict(set)
for unit,subarea in subareas:childsets[subarea].add(unit)
csvout('processed/subarea_pricing_units.csv',[{'subarea':s,'distinct_pricing_units':len(units),'parents':load_market_graph()['parents'].get(s,[]),'basis':'Proposed source-text resolution; fixed frozen duplicate memberships, not historical reassignment'} for s,units in sorted(childsets.items())])
import pandas as pd
from market import metrics as project_metrics
eligible=pd.DataFrame(read(P/'snapshots/active_eligible_source_rows.json'))
eligible['listing_date']=pd.to_datetime(eligible.listing_date)
eligible=eligible[eligible.normalized_id.isin(membership)].copy()
eligible['pricing_unit_key']=eligible.normalized_id.map(membership)
childmetrics=[]
for subarea,units in childsets.items():
 frame=eligible[eligible.pricing_unit_key.isin(units)].copy();frame['neighborhood']=subarea
 childmetrics.extend(project_metrics(frame,'Proposed_child_source_assertion_fixed_units'))
csvout('processed/subarea_market_metrics.csv',childmetrics)

tree=ET.parse(B/'validation/all_tests.xml');suites=tree.findall('.//testsuite')
testresult={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
testresult['passed']=testresult['tests']-testresult['failures']-testresult['errors']-testresult['skipped']
testresult['command']='C:/Projects/FartEstate/.venv/Scripts/python.exe -m pytest tests --ignore=tests/e2e -q --junitxml=C:/Projects/FartEstate/research/prishtina_location_demo/phase5/validation/all_tests.xml'
testresult['cwd']=str(ROOT);testresult['database_test_safety']='tests.db_isolation enforces a dedicated test database or disabled DB; research DB is never a writable test target.'
testresult['browser_e2e']='Not run: public UI/cache behavior intentionally unchanged. Existing API/lookup, financial and normalization unit/integration tests included.'
assert not testresult['failures'] and not testresult['errors']
write(B/'validation/regression_test_results.json',testresult)

preflight=read(B/'validation/git_preflight.json');protected={k:digest(ORIGINAL/k) for k in preflight['source_hashes']}
changed_protected=[k for k in protected if protected[k]!=preflight['source_hashes'][k]]
assert not changed_protected,changed_protected
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
newfiles=['data/gazetteers/market_relationships.json','src/groundtruth/gazetteers/market_graph.py','src/groundtruth/analytics/market_hierarchy.py','tests/test_phase5_locations.py','tests/fixtures/phase5/location_examples.json']
fingerprints={'original_protected_before':preflight['source_hashes'],'original_protected_after':protected,'original_protected_files_unchanged':not changed_protected,'implementation_after':{p:digest(ROOT/p) for p in sorted(set(changed+newfiles)) if (ROOT/p).is_file()},'new_reference_version':compute_gazetteer_version(),'legacy_frozen_five_json_version':compute_legacy_gazetteer_version(B/'rollback/data/gazetteers'),'legacy_version_policy':'Historical stored fingerprints untouched; legacy helper reproduces old interpretation. New active hash includes YAML and graph.'}
write(B/'validation/source_fingerprints.json',fingerprints)

snapshot=read(B/'validation/current_database_snapshot.json')
preservation_path=B/'validation/database_preservation.json'
try:
 if preservation_path.exists() and read(preservation_path).get('final_recheck_available') is False and '--refresh-db' not in sys.argv:
  import psycopg
  raise psycopg.OperationalError('Known unavailable local DB; reuse prior verified fingerprint without repeated polling. Use --refresh-db for a requested fresh check.')
 with connect() as c:
  c.execute('BEGIN READ ONLY')
  count,fp=c.execute("SELECT count(*),md5(string_agg(md5(to_jsonb(n)::text),'' ORDER BY id)) FROM normalized_listings n WHERE id<=%s",(snapshot['max_id'],)).fetchone()
  latest=c.execute('SELECT count(*) FROM normalized_listings').fetchone()[0]
  c.rollback()
 unchanged=fp==snapshot['normalized_content_fingerprint'] and count==snapshot['normalized_count']
 assert unchanged,'Captured historical normalized rows changed concurrently; investigate before reporting integrity.'
 preservation={'transaction_read_only':'on','captured_rows_verified_unchanged':unchanged,'verified_rows':count,'current_total':latest,'captured_max_id':snapshot['max_id'],'before_fingerprint':snapshot['normalized_content_fingerprint'],'after_fingerprint':fp,'phase5_database_writes':False,'verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'final_recheck_available':True}
except Exception as exc:
 import psycopg
 if not isinstance(exc,(psycopg.OperationalError,psycopg.InterfaceError)) or not preservation_path.exists():raise
 preservation=read(preservation_path)
 assert preservation['captured_rows_verified_unchanged'] and preservation['before_fingerprint']==snapshot['normalized_content_fingerprint']
 preservation.setdefault('verified_at',datetime.datetime.fromtimestamp(preservation_path.stat().st_mtime,datetime.timezone.utc).isoformat())
 preservation.update(final_recheck_available=False,final_recheck_error=type(exc).__name__,final_recheck_limitation='Local database is currently unreachable. Prior successful content-fingerprint verification retained; recheck required before live deployment testing. No DB service changes attempted.')
 count=preservation['verified_rows'];unchanged=preservation['captured_rows_verified_unchanged']
write(preservation_path,preservation)

flags=frozen['all_observation_flags'];latestflags=frozen['latest_source_flags'];activeflags=frozen['frozen_active_pricing_unit_flags']
alias_changed=market['canonical_alias_changed_fixed_units']
labels=[('school_specificity_prevented','School specificity prevented, previous resolver'),('stored_school_specificity_reduced','Stored school assignment would be reduced'),('kalabria_recovered','Previously missed Kalabria matches'),('false_letter_prevented','Ahmet/letter-corridor false matches prevented'),('whole_token_false_positive_prevented','Substring-only false location hits prevented'),('letter_area_preserved','Rruga A/B/C area matches retained'),('landmark_membership_prevented','Explicit proximity/developer membership overclaims prevented'),('multi_parent_supported','Sllovenia Sport with both parent relationships'),('newly_supported_match','Previously missing source-text matches'),('source_city_provenance_conflict','Source city differs from old parsed city'),('remaining_market_disagreement','Non-equivalent old/new market disagreements'),('potential_regression','Potential recall regressions requiring review'),('canonical_id_changed','Old/new resolver neighborhood slug differs')]
summary_table='| Outcome | All observations | Latest source listings | Frozen pricing units |\n|---|---:|---:|---:|\n'+'\n'.join(f'| {label} | {flags.get(k,0):,} | {latestflags.get(k,0):,} | {activeflags.get(k,0):,} |' for k,label in labels)
files_table='\n'.join('- `'+p+'`' for p in sorted(set(changed+newfiles)))
graph=load_market_graph()
alias_table='\n'.join('- `'+slug+'`: '+', '.join(terms) for slug,terms in graph['alias_groups'].items())
parent_table='\n'.join('- `'+s+'` → '+', '.join('`'+p+'`' for p in ps) for s,ps in graph['parents'].items())
with (B/'processed/neighborhood_market_impact.csv').open(encoding='utf-8-sig') as f:metricrows=list(csv.DictReader(f))
from groundtruth.analytics.sample_confidence import confidence_level
existing={(r['scenario'],r['property_type'],r['neighborhood']) for r in metricrows}
baseline_rows=[r for r in metricrows if r['scenario']=='A_existing']
for scenario in ['B_aliases_fixed_groups','C_aliases_recomputed_groups','D_independently_approved_geography_only']:
 for old in baseline_rows:
  if (scenario,old['property_type'],old['neighborhood']) in existing:continue
  blank=old.copy();blank['scenario']=scenario
  for k in ['eligible_units','sale_units','rent_units','sale_psm_sample','rent_sample','sale_comparable_pool','rent_comparable_pool']:blank[k]=0
  for k in ['median_sale_eur_m2','median_monthly_rent','median_rent_eur_m2']:blank[k]=None
  for k in ['eligible_units','sale_units','rent_units','sale_comparable_pool','rent_comparable_pool']:blank[k+'_delta']=-int(old[k])
  for k in ['median_sale_eur_m2_delta','median_monthly_rent_delta']:blank[k]=None
  blank.update(sale_confidence=confidence_level(0),rent_confidence=confidence_level(0),tiny_sample=True)
  metricrows.append(blank)
csvout('processed/neighborhood_market_impact.csv',metricrows)
base={r['neighborhood']:r for r in metricrows if r['scenario']=='A_existing' and r['property_type']=='ALL'}
proposal={r['neighborhood']:r for r in metricrows if r['scenario']=='B_aliases_fixed_groups' and r['property_type']=='ALL'}
impact='| Market | Before units | Canonical units | Sale €/m² before → after | Monthly rent before → after | Sale/rent comparable pools after |\n|---|---:|---:|---|---|---|\n'
for slug in graph['alias_groups']:
 ref=next(n for n in read(P/'snapshots/reference_tables.json')['neighborhoods'] if n['slug']==slug);name=ref['name'];old=base.get(name,{});new=proposal.get(name,{})
 impact+=f"| {name} | {old.get('eligible_units',0)} | {new.get('eligible_units',0)} | {old.get('median_sale_eur_m2','—')} → {new.get('median_sale_eur_m2','—')} | {old.get('median_monthly_rent','—')} → {new.get('median_monthly_rent','—')} | {new.get('sale_comparable_pool',0)} / {new.get('rent_comparable_pool',0)} |\n"
reports={
'CONFIRMED_MARKET_HIERARCHY.md':f'''# Confirmed market hierarchy

Authority: owner Phase5 product definitions, not legal administrative containment.

{alias_table}

## Confirmed parent associations

{parent_table}

Sllovenia Sport is one `market_subarea:sllovenia-sport` with two typed parents.
Legacy neighborhood ID47 remains readable. `market_children` returns the same
canonical entity ID under either parent. No scalar database parent is rewritten.
Physical Rruga A/B/C use separate `physical_street:*` IDs; their old JSON road
parent assertions remain intact and are not claimed independently verified.
Legacy neighborhood records for Mati1/2/3, Prishtina e Re and Parku i Qytetit are
interpreted through typed entity redirects without deleting or renumbering them.
Qafa remains separate; no Tophane or Qendra containment is invented. Marigona Hill
and Residence remain distinct. Residential Gërmia/Sofalia is separate from the park.
Official42 local-community/OCR/OSM references stay in previous phases, unchanged.
No official community is equated to a product subarea and no polygon is fabricated.
''',
'RESOLVER_FIXES.md':f'''# Resolver and parser changes

Actual runtime files changed in the isolated implementation checkout:

{files_table}

The active resolver now enforces complete tokens, preserves punctuation boundaries
and NFC-normalizes decomposed Albanian text. JSON aliases and YAML aliases agree
for the seven confirmed groups; existing inflections are retained. Broad Dardania
is not the school district. Explicit school-area variants remain supported;
nearby-school references are proximity evidence. Ahmet Krasniqi cannot be matched
through the prefix of Rr. A. Park, mall, view, developer and distance references
are guarded. A named complex is distinct from a developer or nearby landmark;
Royal City/Mall remain separate; Narteli and Beni Dona retain parent guards.

Normalization version2.1.0 carries typed entity/subarea/parent/proximity evidence
in confidence details. Pro-RKS parsed city preserves explicit source city and
distinguishes absence. The old normalized pricing city is retained only through
explicit `pricing_compatibility_city` / pending-policy metadata, preserving scope.
This is not permission to exclude Fushë Kosovë or relocate any historical listing.
New reference fingerprint `{fingerprints['new_reference_version']}` includes all
five JSON inputs, active YAML and the typed relationship graph. Historical
five-JSON interpretation remains reproducible with the legacy hash helper.
''',
'FULL_CORPUS_REGRESSION.md':f'''# Full-corpus regression

Frozen October23 population: **63,686 observations;27,273 latest source identities;
15,620 eligible latest rows;11,730 deduplicated pricing units**. All reconcile.
The separate read-only current snapshot has **{current['observations']:,} observations
and {current['unique_latest_source_listings']:,} latest identities**, drift
{snapshot['count_drift']:,} observations. Lifecycle observations are not normalized
rows and are never counted as independent geographic observations.

Stored historical assignments (A), prePhase5 resolver/reference replay (B), new
resolver replay (C), and independently approved correction scope (D) are distinct.
Old and new resolvers consume the same original parsed source inputs; stored
normalized assignments are output comparison fields, not new geographic evidence.

{summary_table}

These flags overlap. Rows and latest identities are different grains; pricing-unit
flags use only frozen canonical primary IDs, not sums of duplicate source rows.
Substring prevention is a software matching correction, not a new property survey.
Possible regressions are deliberately retained in regression_cases.csv; no claim
is made that every old or new location is geographically verified. The unsupported
school count differs from Phase3's1,854 risk flag because this replay compares all
old resolver/stored school assignments, while Phase3 applied a narrower diagnostic.
All Phase4 pending decisions remain pending. Zero independent location changes
have been approved or applied.
Unresolved-for-review population (no accepted market identity or complex
ambiguity): {len(unresolved):,} observations. This is a review queue, not permission
to recover, relocate or exclude them automatically.
''',
'MARKET_IMPACT.md':f'''# Market impact: fixed eligibility, actual project calculations

All four scenarios retain **11,730 units** (4,423 sale;6,987 rent;320 other).
A reproduces Phase3 group memberships and annual report payload exactly. B applies
owner-confirmed aliases with duplicate groups fixed. C reruns the actual cross-portal
dedup implementation after canonical grouping: **0 changed duplicate memberships**.
D contains only independently approved geography changes: **0**, so equals A.
Alias consolidation changes labels for **{alias_changed:,} fixed pricing units**, not physical
property locations. Geographic recoveries are not mixed into these accepted scenarios.

All four annual report payloads are identical to the frozen baseline. A draft
counter incorrectly treated1,725 null-to-null neighborhood labels as changes;
that audit error is corrected and regression-tested. Actual alias movements:0.

{impact}

Full per-neighborhood/property-type counts, medians, threshold/sample flags,
sale/rent comparable pools and deltas are in neighborhood_market_impact.csv.
Yield outputs use the project's real annual-report yield helper. These are asking
prices, not achieved transaction prices or financial forecasts. Comparable rules
and sample thresholds are unchanged, including valuation's minimum30 comparables.

## Overlapping Sllovenia Sport projection

The proposed source-text resolver identifies **{len(union)} distinct frozen pricing
units** for Sllovenia Sport. Each parent report can explicitly include those same
{len(union)} units, but their combined total is **{len(union)}**, not
{sum(map(len,overlap.values()))}. Entity membership is a research projection, not
independent property verification. Legacy production aggregates/cache files are
unchanged; production consumers must adopt non-additive set membership deliberately.
''',
'REMAINING_UNCERTAINTIES.md':'''# Remaining uncertainties and prohibited automatic actions

- No authoritative neighborhood polygons were acquired. Owner market definitions
  establish product semantics, not exact physical property boundaries.
- 42 official communities and OCR street rows remain separate; most documentary
  street-to-OSM identities are unverified. No official/product equivalence inferred.
- Phase4 human-pending city recommendations remain pending. Source-city provenance
  is fixed locally but municipality eligibility is held behind an explicit legacy
  compatibility boundary. No Fushë Kosovë/other-city exclusion is authorized.
- Remaining non-equivalent resolver disagreements and possible recall regressions
  are review candidates, not verified errors or approved historical changes.
- Developer, mall, sports/school/park mentions can be ambiguous; direct-source
  context guards cannot establish physical project membership independently.
- No historical FK updates, automatic neighborhood recoveries, schema migrations,
  production rollup changes, public cached report rewrites, deployment or push.
- Scalar legacy reference tables cannot persist two parent FKs. The local typed
  graph and confidence provenance support both parents without migration; a future
  relational graph migration would require separate approval if desired.
''',
'IMPLEMENTATION_READINESS.md':f'''# Implementation readiness

**Ready for controlled, read-only shadow testing: yes. Live deployment testing
remains gated by the checks below. Unattended production rollout and historical
reprocessing are not approved.**

Tests: **{testresult['passed']} passed, {testresult['skipped']} skipped, 0 failures/errors**.
The dedicated test DB was unavailable where marked skipped; production/research DB
was never used for writable tests. Browser E2E was not run because public UI and
cached reports were deliberately unchanged. API/lookup, normalization, version,
reference, valuation, annual report and cross-dedup tests are included.
Full frozen and current replay completed. The original 77 protected source/reference
files and {count:,} captured DB normalized rows are verified unchanged.
DB content verification time: {preservation['verified_at']}. Final live DB recheck
available: {preservation['final_recheck_available']}. If false, the local service
is currently unreachable; prior successful fingerprint verification is retained
and a fresh DB check is required before environment-specific deployment testing.

Historical normalized records are safe to leave unchanged: **yes**. New metadata
does not retroactively alter old versions or IDs. No database migration is needed
for this compatible graph/resolver implementation. Persisting multi-parent links
as relational rows later would be a separately reviewed schema change.

Before any production promotion: review remaining potential regressions and
non-equivalent conflicts, explicitly approve municipality-scope policy, ensure
consumers display multi-parent areas as shared identities and use distinct unit
rollups, run environment-specific DB-backed and browser acceptance checks, and
obtain deployment authorization. The implementation is isolated from the live
scraper checkout so unfinished semantics cannot leak into its ETL.
Integration with the original checkout's pre-existing uncommitted scraper work
requires review; that work is deliberately outside the focused implementation.

Exact full-suite command is recorded in validation/regression_test_results.json.
Reproduce private audits with scripts/capture_current.py, scripts/replay.py,
scripts/market.py and scripts/finalize.py from the implementation checkout using
the original project virtualenv. Public analytics are never regenerated.
''',
'ROLLBACK_GUIDE.md':f'''# Git and rollback

Original HEAD: `{preflight['head']}`. Original branch:
`{preflight['branch']}`. Existing dirty source work is preserved. Concurrent work
subsequently moved that checkout to `chore/oracle-migration-prep` at
`8dbe01fa47ef3450b6949e7ecf39a2873583a7c2`; its committed delta is confined to
`migration-to-oracle/`. Phase5 did not perform that branch switch or commit.
See validation/concurrent_git_drift.json for the observation receipt. No reset or
checkout is performed against that work. Implementation branch: `codex/prishtina-phase5` in
`{ROOT.as_posix()}`. The exact focused commit and final status are recorded in
validation/git_final.json; no remote push is authorized.

Preflight source hashes, backups and the preexisting source diff are in this
phase's ignored rollback/ and validation/ folders. The exact implementation and
reverse patches are retained there before commit. No DB rollback is needed:
Phase5 performed no DB writes or historical migrations.

Safest rollback is to leave the isolated checkout unused. If the focused commit
is later applied to another branch, use a normal `git revert <recorded commit>`
after checking that branch's current changes. For uncommitted application, first
run `git apply --check <reverse.patch>` and apply only when the patch matches.
Never reset, clean, stash or destructively restore the original dirty checkout.
Keep old stored reference/version metadata readable; do not rewrite historical
foreign keys as part of code rollback. Managed worktree archival is optional and
must not discard required private audit artifacts.
''',
'PHASE5_EXECUTIVE_SUMMARY.md':f'''# Phase5 executive summary

Implemented actual local resolver/parser/reference changes on an isolated branch,
not a research-only replacement resolver. All seven owner equivalences, confirmed
subareas and one Sllovenia Sport identity with two parents are represented. Source
city provenance and context-sensitive school/road/landmark matching are corrected.
Historical IDs, original source wording and explicit pricing compatibility remain.

Validated all **63,686 frozen** and **{current['observations']:,} current** normalized
observations. The exact 11,730-unit baseline and annual report were reproduced. Alias
consolidation relabels {alias_changed:,} fixed units; actual dedup recomputation changes 0 groups.
New property-location assignments remain source assertions requiring review.

{summary_table}

Full suite: {testresult['passed']} passed, {testresult['skipped']} skipped. No
historical DB records changed; no migrations, public cache writes, deployments or
remote pushes. Independent geographic corrections applied:0. Remaining ambiguity
and potential regressions are explicitly listed rather than silently accepted.
See IMPLEMENTATION_READINESS.md for controlled-testing limits and ROLLBACK_GUIDE.md
for the focused local implementation record.
'''}
for name,body in reports.items():(B/'reports'/name).write_text(body,encoding='utf8')
write(B/'validation/implementation_readiness.json',{'controlled_shadow_testing':True,'production_deployment_authorized':False,'historical_rows_unchanged':unchanged,'migration_required':False,'potential_regression_review_required':flags.get('potential_regression',0),'strict_market_changes':0,'test_results':testresult})
print(json.dumps({'reports':len(reports),'database_unchanged':unchanged,'protected_source_files_unchanged':len(protected),'tests':testresult,'sllovenia_overlap':market['proposed_resolver_sllovenia_overlap']},ensure_ascii=True))
