"""Independent whole-population, null-safe movement reconciliation."""
from common import *
import sys,collections
import pandas as pd
sys.path.insert(0,str(ROOT/'src'))
from groundtruth.analytics.market_hierarchy import canonical_market_frame,count_market_label_changes
membership={r['normalized_id'] for r in read(P/'processed/active_corpus_membership.json') if r['is_canonical_primary']}
frame=pd.DataFrame(read(P/'snapshots/active_eligible_source_rows.json'));frame=frame[frame.normalized_id.isin(membership)].copy();assert len(frame)==11730
projected=canonical_market_frame(frame,read(P/'snapshots/reference_tables.json')['neighborhoods'])
changes=count_market_label_changes(frame,projected)
transitions=collections.Counter((None if pd.isna(a) else a,None if pd.isna(b) else b) for a,b in zip(frame.neighborhood,projected.neighborhood))
assert sum(transitions.values())==11730
assert sum(v for (a,b),v in transitions.items() if a!=b)==changes
csvout('processed/neighborhood_movements.csv',[{'old':a,'new':b,'units':v,'basis':'Null-safe owner-confirmed alias identity, fixed groups; not property relocation'} for (a,b),v in transitions.items()])
data=read(B/'validation/market_metric_reconciliation.json')
data['canonical_alias_changed_fixed_units']=changes
data['missing_neighborhood_comparison_policy']='Null-to-null is unchanged, not NaN != NaN movement.'
baseline=read(B/'processed/market_A_existing.json')
data['annual_payload_equal_to_baseline']={label:read(B/'processed'/f'market_{label}.json')==baseline for label in ['A_existing','B_aliases_fixed_groups','C_aliases_recomputed_groups','D_independently_approved_geography_only']}
data['movement_validation']={'tested_population':11730,'actual_label_changes':changes,'unknown_labels_retained':int(frame.neighborhood.isna().sum()),'prior_null_comparison_overcount_corrected':True,'independent_population_check':True}
write(B/'validation/market_metric_reconciliation.json',data)
print(json.dumps({'changes':changes,'annual_payload_equal':data['annual_payload_equal_to_baseline'],'missing_labels':int(frame.neighborhood.isna().sum())}))
