"""Application rollback rehearsal on owned loopback QA, never Azure traffic."""
from pathlib import Path
import subprocess,json,time,uuid,httpx
E=Path('C:/Projects/FartEstate/release/readiness/evidence');candidate='metrik-rc-app-20261026';rollback='metrik-rc-rollback-20261026';network='metrik-rc-qa-20261026'
old=json.loads((E/'azure-current-image.json').read_text());image='acrmetrikbetalgy2mu.azurecr.io/metrik-api@'+old['digest']
state=json.loads(subprocess.check_output(['docker','inspect',candidate],text=True))[0];assert state['Config']['Labels']['metrik.rc']=='20261026'
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True)
def ready():
 for _ in range(120):
  try:
   r=httpx.get('http://127.0.0.1:18765/api/ready',timeout=3)
   if r.status_code==200:return True
  except Exception:pass
  time.sleep(1)
 return False
run(['docker','stop',candidate])
env=['APP_ENV=production','DATABASE_URL=postgresql+psycopg://groundtruth_test:groundtruth_test@metrik-rc-testdb-20261026:5432/groundtruth_test','PRODUCT_WRITE_BACKEND=database','RUN_MIGRATIONS_ON_START=false','API_REQUIRE_LOOKUP_CACHE=true','API_DOCS_ENABLED=false','API_RATE_LIMIT_ENABLED=true','PUBLIC_BASE_URL=http://127.0.0.1:18765','TRUSTED_HOSTS=localhost,127.0.0.1','FORWARDED_ALLOW_IPS=127.0.0.1','REQUIRE_SENTRY_DSN=false','HEALTH_CHECK_TOKEN='+uuid.uuid4().hex,'VALUATION_PUBLIC_ENABLED=true']
cmd=['docker','run','-d','--name',rollback,'--network',network,'--label','metrik.rc=20261026','-p','127.0.0.1:18765:8000']
for value in env:cmd+=['-e',value]
try:
 run(cmd+[image]);assert ready(),'Prior production image did not become ready locally'
 response=httpx.get('http://127.0.0.1:18765/api/lookup/neighborhood/ulpiana',timeout=10);assert response.status_code==200
 receipt={'tested_environment':'owned loopback QA only','previous_production_image':image,'previous_image_ready':True,'lookup_status':response.status_code,'production_traffic_changed':False,'migrations':False,'database_target':'owned disposable fixture'}
finally:
 subprocess.run(['docker','stop',rollback],capture_output=True)
 run(['docker','start',candidate])
assert ready(),'Candidate did not recover after local rollback rehearsal'
receipt['candidate_restored_ready']=True
(E/'rollback-qa.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
