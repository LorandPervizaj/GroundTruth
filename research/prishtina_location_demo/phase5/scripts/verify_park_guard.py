"""Scan all replay inputs for the final English park-name suffix guard."""
from replay import *
pattern=re.compile(r'\b(?:germia|germi|germise)\s+park\w*\b')
out={}
for label,path,csvname in [('frozen',P/'snapshots/normalized_inputs.jsonl.gz','phase5_listing_replay.csv'),('current',B/'baseline/current_normalized_inputs.jsonl.gz','phase5_current_listing_replay.csv')]:
 prior={int(r['record_id']):r for r in csv.DictReader((B/'processed'/csvname).open(encoding='utf-8-sig'))}
 checked=0;candidates=0;changed=[]
 for row in rows(path):
  checked+=1;p=row['parsed'] or {};extra=p.get('extra_fields')or{};raw=row.get('raw_location_metadata')or{}
  text=' '.join(str(v or'')for v in [extra.get('title_en')or extra.get('title')or raw.get('title'),p.get('neighborhood_raw'),p.get('street_raw'),p.get('complex_raw'),p.get('description_original'),p.get('city')])
  if not pattern.search(normalize_text(text)):continue
  candidates+=1;now=assess(row);old=prior[row['record_id']]
  if any((now[k] or '')!=old[k]for k in ['new_resolver_neighborhood','new_resolver_subarea','new_resolver_street','new_resolver_complex','new_canonical_market_id','change_category']) or now['flags']!=json.loads(old['flags']):changed.append(row['record_id'])
 out[label]={'all_inputs_scanned':checked,'park_suffix_candidates_reassessed':candidates,'changed_outcomes':changed}
write(B/'validation/park_suffix_regression.json',out)
print(json.dumps(out))
assert not any(v['changed_outcomes'] for v in out.values()),'Park suffix change affects existing outputs; rerun full replay before finalization.'
