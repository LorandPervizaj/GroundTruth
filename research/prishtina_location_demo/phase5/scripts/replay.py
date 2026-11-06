"""Frozen old/new resolver replay plus separately labelled current-data replay."""
from common import *
import sys,importlib.util,collections,re
from types import SimpleNamespace
from dataclasses import asdict
sys.path.insert(0,str(ROOT/'src'))
from groundtruth.gazetteers.location_resolver import LocationResolver,resolve_listing_location
from groundtruth.gazetteers.location_resolver import location_term_matches
from groundtruth.gazetteers.location_tree import normalize_text
from groundtruth.gazetteers.market_graph import load_market_graph,canonical_market_slug,parent_market_slugs
from groundtruth.gazetteers.loader import GazetteerService
from groundtruth.gazetteers.version import compute_gazetteer_version

def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
oldtree=load_module('phase5_old_tree',B/'rollback/src/groundtruth/gazetteers/location_tree.py')
oldtree.get_settings=lambda:SimpleNamespace(gazetteer_dir=B/'rollback/data/gazetteers')
oldmodule=load_module('phase5_old_resolver',B/'rollback/src/groundtruth/gazetteers/location_resolver.py')
oldmodule.normalize_text=oldtree.normalize_text
old=oldmodule.LocationResolver(tree=oldtree.load_location_tree());new=LocationResolver()
refs=read(P/'snapshots/reference_tables.json')
bykind={kind:{r['id']:r['slug'] for r in refs[kind]} for kind in ['neighborhoods','districts','streets','complexes']}
active={r['normalized_id'] for r in read(P/'processed/active_corpus_membership.json') if r['is_canonical_primary']}
citysupp={r['raw_listing_id']:r for r in read(ORIGINAL/'research/prishtina_location_demo/phase4/snapshots/raw_city_metadata.json')}
graph=load_market_graph();N=GazetteerService._canonical_city

def source_city(meta):
 for key in ['property_city','city_raw','normalized_city','city']:
  value=meta.get(key)
  if isinstance(value,dict):value=value.get('name') or value.get('name_en')
  if isinstance(value,str) and value.strip():return value.strip()
 return None

def assess(row):
 p=row['parsed'] or {};n=row['normalized'];extra=p.get('extra_fields') or {};raw=row.get('raw_location_metadata') or {}
 title=extra.get('title_en') or extra.get('title') or raw.get('title')
 kwargs=dict(title=title,neighborhood_raw=p.get('neighborhood_raw'),street_raw=p.get('street_raw'),complex_raw=p.get('complex_raw'),description=p.get('description_original'),city=p.get('city'))
 a=oldmodule.resolve_listing_location(old,**kwargs);c=resolve_listing_location(new,**kwargs)
 text=' '.join(str(x or '') for x in [title,p.get('description_original')]);norm=GazetteerService._normalize(text)
 actualcity=source_city(citysupp.get(row['raw_listing_id'],raw));citydiff=bool(actualcity and p.get('city') and N(actualcity)!=N(p['city']))
 stored=bykind['neighborhoods'].get(n.get('neighborhood_id'))
 alias=bool(a.neighborhood_slug and c.neighborhood_slug and a.neighborhood_slug!=c.neighborhood_slug and canonical_market_slug(a.neighborhood_slug)==canonical_market_slug(c.neighborhood_slug))
 school=a.district_slug=='shkolla-dardania' and c.district_slug!='shkolla-dardania'
 newmatch=not a.neighborhood_slug and bool(c.neighborhood_slug)
 letter=bool(a.district_slug in ['rruga-a','rruga-b','rruga-c'] and a.district_slug!=c.district_slug and 'ahmet krasniqi' in norm)
 selected={('complex',a.complex_slug),('district',a.district_slug),('neighborhood',a.neighborhood_slug)}
 original_norm=normalize_text(text)
 suppressed=[h for h in new._scan_unfiltered(original_norm) if not location_term_matches(original_norm,h.term)]
 landmark=any((h.kind,h.slug) in selected for h in suppressed)
 landmark=landmark and (a.complex_slug!=c.complex_slug or a.district_slug!=c.district_slug or a.neighborhood_slug!=c.neighborhood_slug)
 parents=parent_market_slugs(c.market_subarea_slug)
 parentvalid=bool(c.market_subarea_slug and parents)
 multi=len(parents)>1
 oldcanon=canonical_market_slug(a.neighborhood_slug);newcanon=canonical_market_slug(c.neighborhood_slug)
 related=bool(oldcanon in parents or newcanon in parent_market_slugs(oldcanon) or oldcanon in parent_market_slugs(newcanon))
 conflict=bool(oldcanon and newcanon and oldcanon!=newcanon and not related and not alias)
 evidence_text=normalize_text(' '.join(str(x or '') for x in kwargs.values()))
 oldhits=[h for h in old._scan(oldmodule.normalize_text(' '.join(str(x or '') for x in kwargs.values()))) if (h.kind,h.slug) in selected]
 lexical=bool(a.neighborhood_slug and not c.neighborhood_slug and oldhits and not any(re.search(r'(?<!\w)'+re.escape(h.term)+r'(?!\w)',evidence_text) for h in oldhits))
 regression=bool(a.neighborhood_slug and not c.neighborhood_slug and not landmark and not lexical)
 category='equivalent-name normalization' if alias else 'same neighborhood, reduced unsupported specificity' if school else 'parser false positive corrected' if letter or lexical else 'landmark-only reference' if landmark else 'parser false negative corrected' if newmatch else 'valid multi-parent relationship' if multi else 'valid parent-child relationship' if parentvalid else 'complex identity ambiguity' if c.invalid_location else 'genuine market-area disagreement' if conflict else 'possible regression' if regression else 'source-city provenance corrected' if citydiff else 'evidence insufficient' if not c.neighborhood_slug else 'unchanged product-model assignment'
 flags={'alias_normalized':alias,'school_specificity_prevented':school,'stored_school_specificity_reduced':n.get('district_id')==49 and c.district_slug!='shkolla-dardania','newly_supported_match':newmatch,'kalabria_recovered':newmatch and ('kalabr' in norm),'false_letter_prevented':letter,'letter_area_preserved':c.district_slug in ['rruga-a','rruga-b','rruga-c'],'parent_relationship_supported':parentvalid,'multi_parent_supported':multi,'landmark_membership_prevented':landmark,'complex_ambiguous':c.invalid_location,'source_city_provenance_conflict':citydiff,'remaining_market_disagreement':conflict,'potential_regression':regression,'canonical_id_changed':a.neighborhood_slug!=c.neighborhood_slug}
 flags.update(whole_token_false_positive_prevented=lexical,false_hierarchy_disagreement_removed=bool((alias or related) and a.neighborhood_slug!=c.neighborhood_slug),complex_ambiguity_resolved=bool(a.invalid_location and not c.invalid_location and c.complex_slug))
 result=dict(record_id=row['record_id'],source_listing_id=n['source_listing_id'],source_portal=n['source_website'],original_neighborhood=stored,original_district=bykind['districts'].get(n.get('district_id')),original_street=bykind['streets'].get(n.get('street_id')),original_complex=bykind['complexes'].get(n.get('complex_id')),original_city=n.get('city'),old_resolver_neighborhood=a.neighborhood_slug,old_resolver_district=a.district_slug,new_resolver_neighborhood=c.neighborhood_slug,new_resolver_subarea=c.market_subarea_slug,new_resolver_street=c.physical_street_slug,new_resolver_complex=c.complex_slug,new_resolver_city=actualcity if n['source_website']=='pro-rks' and actualcity else p.get('city'),old_canonical_market_id=('market_neighborhood:'+a.neighborhood_slug) if a.neighborhood_slug else None,new_canonical_market_id=c.market_entity_id,parent_relationships=list(c.parent_relationships),relationship_type='market_subarea_of' if c.market_subarea_slug else 'canonical_alias_of' if alias else 'location_assertion',change_category=category,reason='Deterministic source-text replay; owner-confirmed product semantics and context guards. Independent property verification not inferred.',evidence_class='source_assertion_plus_owner_market_semantics',requires_human_review=bool(conflict or regression or c.invalid_location or citydiff),eligible_for_strict_market_change=False,source_city_raw=actualcity,source_city_present=actualcity is not None,pricing_city_compatibility_preserved=True,flags=flags)
 return result

def run(path,label,expected=None):
 counts=collections.Counter();activecounts=collections.Counter();latest={};conflicts=[];regressions=[];cityrows=[];total=0
 output=B/'processed'/('phase5_listing_replay.csv' if label=='frozen' else 'phase5_current_listing_replay.csv')
 with output.open('w',encoding='utf-8-sig',newline='') as f:
  writer=None
  for row in rows(path):
   r=assess(row);total+=1
   if writer is None:writer=csv.DictWriter(f,fieldnames=list(r));writer.writeheader()
   writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
   counts.update(k for k,v in r['flags'].items() if v);counts['category:'+r['change_category']]+=1
   if row['record_id'] in active:activecounts.update(k for k,v in r['flags'].items() if v)
   key=(r['source_portal'],r['source_listing_id'])
   if key not in latest or latest[key]['record_id']<r['record_id']:latest[key]=r
   if r['flags']['remaining_market_disagreement']:conflicts.append(r)
   if r['flags']['potential_regression']:regressions.append(r)
   if r['flags']['source_city_provenance_conflict']:cityrows.append(r)
   if total%10000==0:print(label,total,flush=True)
 if expected is not None:assert total==expected
 latestcounts=collections.Counter(k for r in latest.values() for k,v in r['flags'].items() if v)
 summary={'observations':total,'unique_latest_source_listings':len(latest),'all_observation_flags':dict(counts),'latest_source_flags':dict(latestcounts),'frozen_active_pricing_unit_flags':dict(activecounts),'frozen_pricing_unit_population':len(active),'strict_market_changes_approved':0,'correction_boundary':'Semantic/context replay; no independent property-location verification; no database mutation or historical correction.'}
 write(B/'validation'/f'{label}_replay_summary.json',summary)
 if label=='frozen':
  csvout('processed/previous_vs_new_outcomes.csv',[{'change_category':k.removeprefix('category:'),'observations':v} for k,v in counts.items() if k.startswith('category:')])
  csvout('processed/remaining_location_conflicts.csv',conflicts);csvout('processed/regression_cases.csv',regressions);csvout('processed/source_city_provenance_results.csv',cityrows)
 return summary

if __name__=='__main__':
 a=run(P/'snapshots/normalized_inputs.jsonl.gz','frozen',63686)
 current=read(B/'validation/current_database_snapshot.json')
 c=run(B/'baseline/current_normalized_inputs.jsonl.gz','current',current['normalized_count'])
 aliases=[]
 refs_by_slug={n['slug']:n for n in refs['neighborhoods']}
 for oldslug,newslug in graph['canonical_redirects'].items():aliases.append({'historical_slug':oldslug,'historical_db_id':refs_by_slug.get(oldslug,{}).get('id'),'canonical_slug':newslug,'canonical_db_id':refs_by_slug.get(newslug,{}).get('id'),'historical_foreign_keys_changed':False})
 csvout('processed/canonical_alias_reconciliation.csv',aliases)
 edges=[e for e in graph['relationships'] if e['predicate']=='market_subarea_of']
 csvout('processed/parent_child_reconciliation.csv',edges)
 csvout('processed/multi_parent_relationships.csv',[e for e in edges if e['subject']=='market_subarea:sllovenia-sport'])
 write(B/'validation/full_corpus_reconciliation.json',{'frozen':a,'current':c,'current_snapshot':current,'reference_fingerprint':compute_gazetteer_version(),'preserved_frozen_input_sha256':digest(P/'snapshots/normalized_inputs.jsonl.gz'),'writes':False,'official_geography_modified':False})
 print(json.dumps({'frozen':a,'current':c},ensure_ascii=True),flush=True)
