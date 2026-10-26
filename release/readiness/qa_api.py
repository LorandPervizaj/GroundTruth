"""Exercise the immutable local image API and privacy boundaries."""
from pathlib import Path
import httpx,json,subprocess,hashlib
E=Path('C:/Projects/FartEstate/release/readiness/evidence');base='http://127.0.0.1:18765'
c=httpx.Client(base_url=base,timeout=30);checks=[]
def check(method,path,expected=200,**kwargs):
 r=c.request(method,path,**kwargs);checks.append({'method':method,'path':path,'status':r.status_code,'expected':expected});assert r.status_code==expected,checks[-1];return r
for path in ['/api/ready','/api/meta','/api/neighborhoods','/api/markets','/api/methodology','/api/rent-yield','/api/lookup/neighborhood/ulpiana','/api/search?q=Ulpiana','/api/compare?neighborhoods=ulpiana,arberia']:
 check('GET',path)
for path in ['/api/metrics','/docs','/openapi.json','/.env','/research/prishtina_location_demo/phase5/processed/phase5_listing_replay.csv','/data/raw','/security/AUDIT_STATUS.md']:
 check('GET',path,404)
r=check('GET','/api/ready');assert r.headers.get('x-content-type-options')=='nosniff';assert 'content-security-policy'in r.headers
check('GET','/api/ready',400,headers={'Host':'untrusted.invalid'})
check('POST','/api/budget-match',json={'listing_type':'rent','max_budget_eur':500,'min_area_sqm':70,'max_area_sqm':90})
check('POST','/api/valuate',json={'valuation_type':'rent','neighborhood':'Ulpiana','area_sqm':78,'bedrooms':2})
check('POST','/api/contact',422,json={'name':'RC'})
check('POST','/api/contact',json={'name':'Release QA','email':'release-qa@example.invalid','topic':'other','message':'Synthetic local release QA persistence check.'})
check('POST','/api/alerts',503,json={'email':'release-qa@example.invalid','neighborhood':'Ulpiana'})
schema=check('GET','/api/lookup/neighborhood/ulpiana').json();forbidden={'phone','email','description_original','raw_payload','raw_html','contact'}
def visit(x):
 if isinstance(x,dict):
  assert not forbidden.intersection(x),forbidden.intersection(x)
  for v in x.values():visit(v)
 elif isinstance(x,list):
  for v in x:visit(v)
visit(schema)
(E/'qa-api.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'privacy_fields_checked':sorted(forbidden),'production_data_used':False},indent=2),encoding='utf8');print(json.dumps(checks))
