"""Start only the owned local release QA app using the frozen image ID."""
from pathlib import Path
import subprocess,json,uuid,time,urllib.request
E=Path('C:/Projects/FartEstate/release/readiness/evidence');ident=json.loads((E/'release-identity.json').read_text())
assert ident.get('build_exit_code')==0
image=ident['image_config_id'];network='metrik-rc-qa-20261026';db='metrik-rc-testdb-20261026';app='metrik-rc-app-20261026'
def run(args):return subprocess.check_output(args,text=True).strip()
prior=subprocess.run(['docker','inspect',app],capture_output=True,text=True)
if prior.returncode==0:
 old=json.loads(prior.stdout)[0];assert old['Config']['Labels'].get('metrik.rc')=='20261026' and not old['State']['Running']
 (E/'failed-image-startup.log').write_text(subprocess.run(['docker','logs',app],capture_output=True,text=True).stderr,encoding='utf8')
 subprocess.run(['docker','rm',app],check=True,capture_output=True)
known=subprocess.run(['docker','network','inspect',network],capture_output=True,text=True)
if known.returncode:run(['docker','network','create','--label','metrik.rc=20261026',network])
else:assert json.loads(known.stdout)[0]['Labels'].get('metrik.rc')=='20261026'
if network not in json.loads(run(['docker','inspect',db]))[0]['NetworkSettings']['Networks']:
 subprocess.run(['docker','network','connect',network,db],check=True)
token=uuid.uuid4().hex
env={'APP_ENV':'production','DATABASE_URL':f'postgresql+psycopg://groundtruth_test:groundtruth_test@{db}:5432/groundtruth_test','HEALTH_CHECK_TOKEN':token,'PRODUCT_WRITE_BACKEND':'database','API_REQUIRE_LOOKUP_CACHE':'true','API_DOCS_ENABLED':'false','API_RATE_LIMIT_ENABLED':'true','RUN_MIGRATIONS_ON_START':'false','REQUIRE_SENTRY_DSN':'false','PUBLIC_BASE_URL':'http://127.0.0.1:18765','TRUSTED_HOSTS':'localhost,127.0.0.1','FORWARDED_ALLOW_IPS':'127.0.0.1','VALUATION_PUBLIC_ENABLED':'true','ALERTS_SIGNUP_ENABLED':'false'}
cmd=['docker','run','-d','--name',app,'--network',network,'--label','metrik.rc=20261026','-p','127.0.0.1:18765:8000']
for k,v in env.items():cmd+=['-e',k+'='+v]
cid=run(cmd+[image]);ready=False
for _ in range(120):
 try:
  with urllib.request.urlopen('http://127.0.0.1:18765/api/ready',timeout=3)as r:ready=r.status==200
  if ready:break
 except Exception:pass
 time.sleep(1)
receipt={'container':app,'container_id':cid,'image_id':image,'image_digest':ident.get('image_manifest_digest'),'network':network,'db_container':db,'loopback_origin':'http://127.0.0.1:18765','production_mode':True,'production_data_used':False,'migrations_on_start':False,'ready':ready,'local_test_credential_policy':'Synthetic test credentials only; no production secrets copied.'}
(E/'qa-start.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
raise SystemExit(0 if ready else 1)
