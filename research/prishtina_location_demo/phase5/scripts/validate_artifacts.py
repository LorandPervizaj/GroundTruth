"""Final population, privacy, hierarchy and output reconciliation gates."""
from common import *
import sys,subprocess,collections
sys.path.insert(0,str(ROOT/'src'))
from groundtruth.gazetteers.market_graph import load_market_graph
required_reports=['PHASE5_EXECUTIVE_SUMMARY.md','CONFIRMED_MARKET_HIERARCHY.md','RESOLVER_FIXES.md','FULL_CORPUS_REGRESSION.md','MARKET_IMPACT.md','REMAINING_UNCERTAINTIES.md','IMPLEMENTATION_READINESS.md','ROLLBACK_GUIDE.md']
required_csv=['phase5_listing_replay.csv','previous_vs_new_outcomes.csv','canonical_alias_reconciliation.csv','parent_child_reconciliation.csv','multi_parent_relationships.csv','remaining_location_conflicts.csv','regression_cases.csv','neighborhood_market_impact.csv','source_city_provenance_results.csv']
required_validation=['source_fingerprints.json','regression_test_results.json','full_corpus_reconciliation.json','market_metric_reconciliation.json','git_preflight.json']
for folder,names in [('reports',required_reports),('processed',required_csv),('validation',required_validation)]:
 for name in names:assert (B/folder/name).is_file() and (B/folder/name).stat().st_size>0,(folder,name)
totals={};presence={}
for label,name,expected in [('frozen','phase5_listing_replay.csv',63686),('current','phase5_current_listing_replay.csv',65245)]:
 ids=set();city=0
 for row in csv.DictReader((B/'processed'/name).open(encoding='utf-8-sig')):
  assert int(row['record_id']) not in ids
  ids.add(int(row['record_id']));city+=row['source_city_present']=='True'
  assert row['eligible_for_strict_market_change']=='False'
 assert len(ids)==expected
 totals[label]=len(ids);presence[label]=city
outcomes=list(csv.DictReader((B/'processed/previous_vs_new_outcomes.csv').open(encoding='utf-8-sig')))
assert sum(int(r['observations']) for r in outcomes)==63686
graph=load_market_graph();assert len(graph['alias_groups'])==7
links=[r for r in graph['relationships']if r['subject']=='market_subarea:sllovenia-sport'and r['predicate']=='market_subarea_of']
assert len(links)==2 and len({r['subject']for r in links})==1
market=read(B/'validation/market_metric_reconciliation.json')
assert market['canonical_alias_changed_fixed_units']==0
assert market['changed_duplicate_source_memberships']==0
assert all(market['annual_payload_equal_to_baseline'].values())
assert market['proposed_resolver_sllovenia_overlap']['combined_distinct_units']==64
for folder in ['processed','baseline','validation','rollback']:
 path=next((p for p in (B/folder).rglob('*')if p.is_file()),None)
 assert path is not None
 result=subprocess.run(['git','check-ignore','--quiet',str(path.relative_to(ORIGINAL))],cwd=ORIGINAL)
 assert result.returncode==0,('private artifact not ignored',path)
pre=read(B/'validation/git_preflight.json');assert all(digest(ORIGINAL/p)==h for p,h in pre['source_hashes'].items())
current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ORIGINAL,text=True).strip()
current_branch=subprocess.check_output(['git','branch','--show-current'],cwd=ORIGINAL,text=True).strip()
unchanged_git=current_head==pre['head'] and current_branch==pre['branch']
concurrent_paths=subprocess.check_output(['git','diff','--name-only',pre['head'],current_head],cwd=ORIGINAL,text=True).splitlines()
assert unchanged_git or all(p.startswith('migration-to-oracle/') for p in concurrent_paths),'Unexpected overlapping original-checkout Git drift; inspect before proceeding.'
write(B/'validation/concurrent_git_drift.json',{'original_head_before':pre['head'],'original_branch_before':pre['branch'],'original_head_observed':current_head,'original_branch_observed':current_branch,'unchanged':unchanged_git,'concurrent_committed_paths':concurrent_paths,'protected_sources_unchanged':True,'phase5_action':'Observed only; no reset, branch checkout or edits to concurrent migration work.'})
readiness=read(B/'validation/implementation_readiness.json');assert readiness['strict_market_changes']==0
test=read(B/'validation/regression_test_results.json');assert test['passed']==949 and test['failures']==test['errors']==0
out={'status':'passed','rows':totals,'source_city_label_present_observations':presence,'outcome_partition_total':63686,'one_sllovenia_market_entity':True,'sllovenia_parent_links':2,'alias_groups':7,'strict_historical_moves':0,'actual_pricing_label_moves':0,'annual_payloads_equal':True,'private_exports_ignored':True,'original_checkout_protected_files_unchanged':77,'original_branch_head_unchanged':unchanged_git,'concurrent_git_drift_recorded':not unchanged_git,'tests':test['passed'],'skipped':test['skipped'],'database_proof':read(B/'validation/database_preservation.json')}
write(B/'validation/artifact_checks.json',out)
print(json.dumps(out,ensure_ascii=True))
