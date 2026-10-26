"""Actual project metrics and dedup, using fixed frozen eligibility inputs."""
from common import *
import sys,ast,collections
import pandas as pd
sys.path.insert(0,str(ROOT/'src'))
from groundtruth.analytics.cross_dedup import apply_cross_dedupe
from groundtruth.analytics.annual_report import build_annual_report_from_dataframe,_neighborhood_yield_rankings
from groundtruth.analytics.market_metrics import sale_psm_series,rent_psm_series,sane_rent_rows,median_sale_psm
from groundtruth.analytics.sample_confidence import confidence_level
from groundtruth.analytics.display_rounding import round_rent_eur
from groundtruth.analytics import valuation
from groundtruth.analytics.market_hierarchy import canonical_market_frame,count_market_label_changes
from groundtruth.gazetteers.market_graph import load_market_graph,canonical_market_slug,distinct_rollup_memberships

# Reuse the audited Phase4 metric table formatter, which calls the real project
# financial helpers. No static replacement formulas or public cache writes.
helper_path=ORIGINAL/'research/prishtina_location_demo/phase4/scripts/market.py'
module=ast.parse(helper_path.read_text(encoding='utf8'))
exec(compile(ast.Module(body=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in ['safe','metrics']],type_ignores=[]),str(helper_path),'exec'),globals())

def canonicalize(frame,refs):
 return canonical_market_frame(frame,refs['neighborhoods'])

if __name__=='__main__':
 refs=read(P/'snapshots/reference_tables.json');byid={r['id']:r for r in refs['neighborhoods']};byslug={r['slug']:r for r in refs['neighborhoods']};slugs={r['name']:r['slug'] for r in refs['neighborhoods']}
 df=pd.DataFrame(read(P/'snapshots/active_eligible_source_rows.json'));df['listing_date']=pd.to_datetime(df.listing_date)
 assert len(df)==15620
 print('Actual baseline cross-dedup',flush=True)
 tagged=apply_cross_dedupe(df.copy());A=tagged[tagged.is_canonical_primary].copy();assert len(A)==11730
 expected={r['normalized_id']:(r['canonical_group_id'],r['is_canonical_primary']) for r in read(P/'processed/active_corpus_membership.json')}
 baseline_membership_equal=all(expected[r.normalized_id]==(r.canonical_group_id,r.is_canonical_primary) for r in tagged.itertuples());assert baseline_membership_equal
 Bfixed=canonicalize(A,refs)
 print('Actual proposed canonical-group cross-dedup',flush=True)
 proposal=canonicalize(df,refs);newtag=apply_cross_dedupe(proposal);C=newtag[newtag.is_canonical_primary].copy()
 frames={'A_existing':A,'B_aliases_fixed_groups':Bfixed,'C_aliases_recomputed_groups':C,'D_independently_approved_geography_only':A.copy()}
 cutoff=datetime.date(2025,10,23);allmetrics=[];summary=[];payloads={}
 for label,frame in frames.items():
  payload=safe(build_annual_report_from_dataframe(frame,cutoff_date=cutoff,neighborhood_slug_by_name=slugs));payloads[label]=payload
  write(B/'processed'/f'market_{label}.json',payload)
  allmetrics.extend(metrics(frame,label))
  write(B/'processed'/f'yields_{label}.json',safe(_neighborhood_yield_rankings(frame,neighborhood_slug_by_name=slugs,limit=1000)))
  summary.append({'scenario':label,'pricing_units':len(frame),'sale_units':int((frame.listing_type=='sale').sum()),'rent_units':int((frame.listing_type=='rent').sum()),'independently_verified_geographic_moves':0,'eligibility_source_rows':len(df),'asking_prices_only':True})
 oldpayload=read(P/'processed/market_A_existing.json');annual_baseline_equal=payloads['A_existing']==oldpayload;assert annual_baseline_equal
 assert payloads['D_independently_approved_geography_only']==oldpayload
 base={(r['property_type'],r['neighborhood']):r for r in allmetrics if r['scenario']=='A_existing'}
 for r in allmetrics:
  old=base.get((r['property_type'],r['neighborhood']),{})
  for k in ['eligible_units','sale_units','rent_units','sale_comparable_pool','rent_comparable_pool']:r[k+'_delta']=r[k]-old.get(k,0)
  for k in ['median_sale_eur_m2','median_monthly_rent']:
   r[k+'_delta']=r[k]-old[k] if r.get(k) is not None and old.get(k) is not None else None
 csvout('processed/neighborhood_market_impact.csv',allmetrics)
 groupsA={r.normalized_id:frozenset(tagged[tagged.canonical_group_id==r.canonical_group_id].normalized_id) for r in tagged.itertuples()}
 groupsC={r.normalized_id:frozenset(newtag[newtag.canonical_group_id==r.canonical_group_id].normalized_id) for r in newtag.itertuples()}
 changed=[{'normalized_id':i,'old_members':sorted(groupsA[i]),'new_members':sorted(groupsC[i])} for i in groupsA if groupsA[i]!=groupsC[i]]
 csvout('processed/changed_duplicate_memberships.csv',changed)
 transitions=collections.Counter()
 old_names={r.normalized_id:(None if pd.isna(r.neighborhood) else r.neighborhood) for r in A.itertuples()}
 for r in Bfixed.itertuples():transitions[(old_names[r.normalized_id],None if pd.isna(r.neighborhood) else r.neighborhood)]+=1
 csvout('processed/neighborhood_movements.csv',[{'old':k[0],'new':k[1],'units':v,'basis':'Owner-confirmed alias identity, fixed groups; not property relocation'} for k,v in transitions.items()])
 rollups=[]
 districtrefs={r['id']:r['slug'] for r in refs['districts']}
 for label,frame in frames.items():
  unit_subareas=[]
  for r in frame.to_dict('records'):
   neighborhood=byid.get(r.get('neighborhood_id'),{}).get('slug')
   district=districtrefs.get(r.get('district_id'))
   subarea=district if district in load_market_graph()['parents'] else neighborhood if neighborhood in load_market_graph()['parents'] else None
   if subarea:unit_subareas.append((str(r.get('canonical_group_id') or r['normalized_id']),subarea))
  membership=distinct_rollup_memberships(unit_subareas)
  union=set.union(*membership.values()) if membership else set()
  rollups.append({'scenario':label,'child_unit_links':len(unit_subareas),'distinct_child_units':len({u for u,s in unit_subareas}),'parent_counts':{k:len(v) for k,v in membership.items()},'combined_parent_union':len(union),'sum_parent_memberships_nonadditive':sum(map(len,membership.values())),'double_counting_avoided':len(union)==len({u for u,s in unit_subareas})})
 assert all(r['double_counting_avoided'] for r in rollups)
 write(B/'processed/overlapping_subarea_rollups.json',rollups)
 result={'baseline_eligible_rows':15620,'baseline_pricing_units':11730,'baseline_memberships_exact':baseline_membership_equal,'baseline_annual_report_exact':annual_baseline_equal,'scenarios':summary,'changed_duplicate_source_memberships':len(changed),'canonical_alias_changed_fixed_units':sum(old!=new for (old,new),v in transitions.items() for _ in range(v)),'geographic_correction_policy':'Scenario D applies zero independently verified location changes; Phase4 human-pending proposals remain pending. Parent rollups are explicit nonadditive research projections, production aggregation unchanged.','metric_helper_sha256':digest(helper_path),'overlap_rollups':rollups,'public_caches_written':False}
 result['annual_payload_equal_to_baseline']={label:payload==oldpayload for label,payload in payloads.items()}
 result['canonical_alias_changed_fixed_units']=count_market_label_changes(A,Bfixed)
 result['missing_neighborhood_comparison_policy']='Null labels compare equal to null labels; never count NaN != NaN as a movement.'
 write(B/'validation/market_metric_reconciliation.json',result)
 print(json.dumps(result,ensure_ascii=True),flush=True)
