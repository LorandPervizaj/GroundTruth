"""Classify the exact Phase5 recall queue without changing historical data."""
from pathlib import Path
import sys,csv,gzip,json,collections,re,hashlib
R=Path('C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate');O=Path('C:/Projects/FartEstate');E=O/'release/readiness/evidence'
sys.path.insert(0,str(R/'src'))
from groundtruth.gazetteers.location_resolver import LocationResolver,resolve_listing_location
from groundtruth.gazetteers.location_tree import normalize_text
P=O/'research/prishtina_location_demo'
cases={int(r['record_id']):r for r in csv.DictReader((P/'phase5/processed/regression_cases.csv').open(encoding='utf-8-sig'))}
assert len(cases)==257
active={r['normalized_id'] for r in json.loads((P/'phase3/processed/active_corpus_membership.json').read_text())if r['is_canonical_primary']}
resolver=LocationResolver();out=[]
with gzip.open(P/'phase3/snapshots/normalized_inputs.jsonl.gz','rt',encoding='utf8')as f:
 for line in f:
  row=json.loads(line);rid=row['record_id']
  if rid not in cases:continue
  p=row['parsed']or{};x=p.get('extra_fields')or{};raw=row.get('raw_location_metadata')or{}
  title=x.get('title_en')or x.get('title')or raw.get('title')
  kwargs=dict(title=title,neighborhood_raw=p.get('neighborhood_raw'),street_raw=p.get('street_raw'),complex_raw=p.get('complex_raw'),description=p.get('description_original'),city=p.get('city'))
  result=resolve_listing_location(resolver,**kwargs)
  assert result.neighborhood_slug==cases[rid]['new_resolver_neighborhood'] or (not result.neighborhood_slug and not cases[rid]['new_resolver_neighborhood'])
  text=normalize_text(' '.join(str(v or'')for v in kwargs.values()))
  explicit_mati=bool(re.search(r'\bmati(?:qan|can|qani|cani)\b',text))
  reason='ambiguous complex/landmark evidence cannot establish neighborhood membership'
  classification='unresolved_requires_stronger_evidence'
  if cases[rid]['old_resolver_neighborhood']=='matiqan' and not explicit_mati:
   classification='conservative_removal_of_inferred_neighborhood'
   reason='Old Matiqan assignment depended on complex/brand/corridor inference; no explicit Matiqan token in original source fields. Not a proven property relocation.'
  out.append({'record_id':rid,'frozen_pricing_primary':rid in active,'old_neighborhood':cases[rid]['old_resolver_neighborhood'],'new_neighborhood':result.neighborhood_slug,'classification':classification,'reason':reason,'source_fields_sha256':hashlib.sha256(json.dumps(kwargs,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'approved_historical_change':False})
assert len(out)==257 and sum(r['frozen_pricing_primary']for r in out)==113
(E/'recall-case-classification.json').write_text(json.dumps(out,indent=2),encoding='utf8')
summary={'reviewed_observations':len(out),'frozen_pricing_units':113,'classification_counts':dict(collections.Counter(r['classification']for r in out)),'confirmed_software_regressions':0,'scope':'Exact Phase5 queue, deterministic original-source context review. Conservative removals are not independently verified geographic false positives; unresolved cases remain review-only.','historical_writes':0,'phase5_market_evidence':json.loads((P/'phase5/validation/market_metric_reconciliation.json').read_text())['movement_validation']}
(E/'regression-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
