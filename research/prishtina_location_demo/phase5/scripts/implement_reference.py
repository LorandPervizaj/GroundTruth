"""Owner-confirmed market semantics; preserve all historical reference IDs."""
import json
from pathlib import Path
import yaml
from render_reference import render_yaml
W=Path('C:/Users/lorandp/.codex/worktrees/prishtina-phase5/FartEstate')
D=W/'data/gazetteers'
def read(name):return json.loads((D/name).read_text(encoding='utf8'))
def write(name,data):(D/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
groups={
 'arberia':['Arbëria','Arberia','Dragodan','Dragodani'],
 'emshir':['Kalabria','Kalabri','Emshir','Emshiri','Emshire','Në Kalabri','Në Emshir'],
 'pejton-lakrishte':['Pejton','Lakrishta','Lakrishte','Lakërishta'],
 'vranjevc-kodra-trimave':['Vranjevc','Vranjevci','Kodra e Trimave'],
 'llullat-dodona':['Dodona','4 Llullat','4 Lullat','Llullat'],
 'sofalia':['Sofalia','Sofali','Gërmia','Germia','Gërmi','Germi'],
 'bregu-i-diellit':['Bregu i Diellit','Sunny Hill'],
}
redirects={'dragodan':'arberia','kalabria':'emshir','lakrishte':'pejton-lakrishte','pejton':'pejton-lakrishte','kodra-e-trimave':'vranjevc-kodra-trimave','dodona':'llullat-dodona','llullat':'llullat-dodona','germia':'sofalia','sunny-hill':'bregu-i-diellit'}
ns=read('neighborhoods.json');by={n['slug']:n for n in ns}
by['sllovenia-sport']['aliases']=list(dict.fromkeys(by['sllovenia-sport'].get('aliases',[])+['Sllovenia e Sportit','Sllovenia Sportit','Slovenia e Sportit']))
for slug,terms in {'bregu-i-diellit':['Bregun','Bregun e Dilliet'],'aktash-muhaxhere':['Muhagjerve'],'ulpiana':['Ulpian'],'sofalia':['Gerrmi']}.items():
 by[slug]['aliases']=list(dict.fromkeys(by[slug].get('aliases',[])+terms))
for slug,aliases in groups.items():by[slug]['aliases']=list(dict.fromkeys(by[slug].get('aliases',[])+aliases))
for old,new in redirects.items():by[old]['canonical_slug']=new
write('neighborhoods.json',ns)
districts=read('districts.json')
for d in districts:
 if d['slug']=='shkolla-dardania':d['aliases']=['Shkollës Dardania','Shkollen Dardania','Shkolles Dardania','Shkolla Dardani','Sh.F.M.U. Dardania']
write('districts.json',districts)
path=D/'draft/prishtina_location_tree.yaml';tree=yaml.safe_load(path.read_text(encoding='utf8'))
for n in tree['city']['neighborhoods']:
 slug=n['slug']
 # Whole-token matching must retain the inflected aliases already supported by
 # the JSON path (Spitalit, Muhaxherëve, etc.), rather than lose valid recall.
 equivalents=[row for row in ns if row['slug']==slug or redirects.get(row['slug'])==slug or row.get('canonical_slug')==slug]
 existing_terms=[term for row in equivalents for term in [row['name'],*row.get('aliases',[])]]
 n['aliases']=list(dict.fromkeys(n.get('aliases',[])+existing_terms))
 if slug=='dardania':n['aliases']=list(dict.fromkeys(n.get('aliases',[])+['Dardani','Dardanisë','Dardanise']))
 if slug in groups:n['aliases']=list(dict.fromkeys(n.get('aliases',[])+groups[slug]))
 for d in n.get('districts',[]):
  if d['slug']=='shkolla-dardania':d['aliases']=['Shkollës Dardania','Shkollen Dardania','Shkolles Dardania','Shkolla Dardani','Sh.F.M.U. Dardania']
  if d['slug']=='germia-sofalia':d['resolution_enabled']=False
  if d['slug'] in ['rruga-a','rruga-b','rruga-c']:
   letter=d['slug'][-1].upper();d['aliases']=list(dict.fromkeys(d.get('aliases',[])+[f'Rr. {letter}',f'Rrugën {letter}',f'Rrugës {letter}',f'Rrugen {letter}',f'Rruges {letter}']))
  if d['slug']=='parku-i-qytetit-aktash':d['aliases']=['Parkun e Qytetit','Parkut të Qytetit']
 for cx in [*n.get('complexes_direct',[]),*[cx for d in n.get('districts',[]) for cx in d.get('complexes',[])]]:
  match=next((r for r in read('complexes.json') if r['slug']==cx['slug']),None)
  if match:cx['aliases']=list(dict.fromkeys(cx.get('aliases',[])+[match['name'],*match.get('aliases',[])]))
if not any(n['slug']=='sllovenia-sport' for n in tree['city']['neighborhoods']):
 tree['city']['neighborhoods'].append({'name':'Sllovenia Sport','slug':'sllovenia-sport','aliases':by['sllovenia-sport']['aliases'],'market_entity_type':'market_subarea','legacy_neighborhood_id':47})
tree['city']['neighborhoods_tbd']=[n for n in tree['city'].get('neighborhoods_tbd',[]) if n['slug'] not in {'sllovenia-sport','sunny-hill','germia'}]
tree['version']='phase5-market-1';tree['updated']='2026-10-26'
for example in tree.get('resolution',{}).get('examples',[]):
 if example.get('text')=='Royal Mall':example['text']='Banesë në kompleksin Royal Mall'
path.write_text(render_yaml(tree,Path('C:/Projects/FartEstate/research/prishtina_location_demo/phase5/rollback/data/gazetteers/draft/prishtina_location_tree.yaml')),encoding='utf8')
parents={'prishtina-e-re':['veternik'],'parku-i-qytetit-aktash':['aktash-muhaxhere'],'sllovenia-sport':['aktash-muhaxhere','qendra'],**{s:['matiqan'] for s in ['mati-1','mati-2','mati-3','rruga-a','rruga-b','rruga-c','muharrem-fejza','ndue-perlleshi']}}
entities={f'market_neighborhood:{s}':{'slug':s,'type':'market_neighborhood','legacy_id':by[s]['id']} for s in by if s not in parents}
relationships=[]
for s,ps in parents.items():
 child=f'market_subarea:{s}';entities[child]={'slug':s,'type':'market_subarea','legacy_neighborhood_id':by.get(s,{}).get('id')}
 for p in ps:relationships.append({'subject':child,'predicate':'market_subarea_of','object':f'market_neighborhood:{p}','evidence':'owner_confirmed_product_semantics_20261026'})
for s in ['rruga-a','rruga-b','rruga-c']:
 road=f'physical_street:{s}';entities[road]={'slug':s,'type':'physical_street','legacy_relationship_policy':'Preserve JSON street parent assertions separately; no verified physical relocation.'}
 relationships.append({'subject':f'market_subarea:{s}','predicate':'corridor_named_after_street','object':road,'evidence':'owner_confirmed_entity_type_distinction'})
for old,new in redirects.items():relationships.append({'subject':f'market_neighborhood:{old}','predicate':'canonical_alias_of','object':f'market_neighborhood:{new}','evidence':'owner_confirmed_product_equivalence'})
for filename,kind in [('complexes.json','residential_complex'),('streets.json','physical_street'),('building_aliases.json','building')]:
 for row in read(filename):
  entity=f'{kind}:{row["slug"]}';entities.setdefault(entity,{'slug':row['slug'],'type':kind,'legacy_id':row.get('id'),'reference_provenance':'existing_JSON_assertion_not_independently_verified'})
  if kind=='residential_complex' and row.get('neighborhood_slug'):
   parent=row['neighborhood_slug'];parent=redirects.get(parent,parent)
   relationships.append({'subject':entity,'predicate':'complex_in_market_area','object':f'market_neighborhood:{parent}','evidence':'existing_JSON_reference_assertion_not_new_geographic_verification'})
graph={'version':'phase5-market-1','entity_types':['municipality','settlement','market_neighborhood','market_subarea','physical_street','street_corridor_market_area','residential_complex','building','official_local_community','landmark','administrative_area'],'relationship_types':['same_market_identity','canonical_alias_of','market_subarea_of','market_area_overlaps','physical_street_in_area','corridor_named_after_street','complex_in_market_area','building_in_complex','near_landmark','official_street_in_local_community','possible_same_geographic_entity'],'entities':entities,'relationships':relationships,'alias_groups':groups,'canonical_redirects':redirects,'parents':parents,'provenance':'Owner product-market definitions, Phase5. Official geography is separate; no new property verification or boundaries.'}
legacy_subareas={'mati':'mati-1','mati-2':'mati-2','mati-3':'mati-3','prishtina-e-re':'prishtina-e-re','parku-i-qytetit':'parku-i-qytetit-aktash','sllovenia-sport':'sllovenia-sport'}
graph['entity_redirects']={f'market_neighborhood:{old}':f'market_subarea:{new}' for old,new in legacy_subareas.items()}
for legacy,subarea in legacy_subareas.items():
 entities[f'market_subarea:{subarea}']['legacy_neighborhood_id']=by[legacy]['id']
 if f'market_neighborhood:{legacy}' in entities:entities[f'market_neighborhood:{legacy}']['canonical_entity_id']=f'market_subarea:{subarea}'
for d in districts:
 entities.setdefault('market_subarea:'+d['slug'],{'slug':d['slug'],'type':'market_subarea','legacy_district_id':d['id'],'legacy_parent_assertion':d['neighborhood_slug'],'reference_provenance':'legacy_JSON_market_tree_not_new_property_verification'})
for s in ['rruga-a','rruga-b','rruga-c']:entities[f'market_subarea:{s}']['roles']=['market_subarea','street_corridor_market_area']
for s,name in [('germia-park','Gërmia Park'),('parku-i-qytetit','Parku i Qytetit'),('sllovenia-sport','Sllovenia Sport'),('shkolla-dardania','Shkolla Dardania'),('royal-mall','Royal Mall'),('maxi-24','Maxi 24')]:
 entities['landmark:'+s]={'slug':s,'name':name,'type':'landmark','policy':'Source proximity is not market membership; no polygon or property verification supplied.'}
write('market_relationships.json',graph)
print('Reference semantics generated; IDs retained; no DB writes.')
