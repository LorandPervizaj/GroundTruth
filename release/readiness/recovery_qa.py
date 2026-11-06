"""Disposable DB recovery drill; production is never a target."""
from pathlib import Path
import json,subprocess,time,hashlib,httpx
E=Path('C:/Projects/FartEstate/release/readiness/evidence');db='metrik-rc-testdb-20261026';user='groundtruth_test';name='groundtruth_test';base='http://127.0.0.1:18765'
state=json.loads(subprocess.check_output(['docker','inspect',db],text=True))[0]
assert state['Config']['Labels'].get('metrik.rc')=='20261026'
assert json.loads((E/'qa-start.json').read_text())['db_container']==db
def run(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,**kwargs)
def sql(query,database=name):return run(['docker','exec',db,'psql','-U',user,'-d',database,'-Atc',query]).stdout.decode().strip()
fingerprint="SELECT count(*),md5(coalesce(string_agg(to_jsonb(p)::text,'' ORDER BY id),'')) FROM product_submissions p"
before=sql(fingerprint)
dump=run(['docker','exec',db,'pg_dump','-U',user,'-d',name,'-Fc']).stdout
(E/'disposable-qa.dump').write_bytes(dump)
run(['docker','exec',db,'createdb','-U',user,'groundtruth_rc_restore_test'])
run(['docker','exec','-i',db,'pg_restore','-U',user,'-d','groundtruth_rc_restore_test','--no-owner','--exit-on-error'],input=dump)
assert sql(fingerprint,'groundtruth_rc_restore_test')==before
receipt={'target':'owned disposable QA database only','production_data_used':False,'backup_sha256':hashlib.sha256(dump).hexdigest(),'restored_product_count_and_fingerprint_equal':True,'before_count_and_fingerprint':before}
(E/'recovery-qa-progress.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
run(['docker','stop',db])
try:
 c=httpx.Client(base_url=base,timeout=20)
 receipt['db_down_cached_lookup_status']=c.get('/api/lookup/neighborhood/ulpiana').status_code
 receipt['db_down_readiness_status']=c.get('/api/ready').status_code
 body={'name':'QA outage','email':'qa-outage@example.invalid','message':'Synthetic local outage persistence check.'}
 response=c.post('/api/contact',json=body)
 receipt['db_down_write_status']=response.status_code
 assert receipt['db_down_cached_lookup_status']==200
 assert receipt['db_down_write_status']==503,response.text
 retry=c.post('/api/contact',json=body)
 receipt['identical_retry_during_outage_status']=retry.status_code
 assert retry.status_code==503,retry.text
finally:
 (E/'recovery-qa-progress.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
 run(['docker','start',db])
for _ in range(30):
 if subprocess.run(['docker','exec',db,'pg_isready','-h','127.0.0.1','-U',user,'-d',name],capture_output=True).returncode==0:break
 time.sleep(1)
# The owned tmpfs test DB deliberately has no durable volume. Restore its fixture.
run(['docker','exec','-i',db,'pg_restore','-U',user,'-d',name,'--clean','--if-exists','--no-owner','--exit-on-error'],input=dump)
assert sql(fingerprint)==before
receipt['post_restart_restore_fingerprint_equal']=True
for _ in range(20):
 if httpx.get(base+'/api/ready',timeout=10).status_code==200:break
 time.sleep(1)
receipt['recovered_readiness_status']=httpx.get(base+'/api/ready',timeout=10).status_code
assert receipt['recovered_readiness_status']==200
retry=httpx.post(base+'/api/contact',json=body,timeout=20)
receipt['identical_retry_after_recovery_status']=retry.status_code
receipt['identical_retry_after_recovery_result']=retry.json().get('status')
assert retry.status_code==200 and retry.json().get('status')=='ok',retry.text
receipt['recovered_write_durable_count']=sql('SELECT count(*) FROM product_submissions')
assert int(receipt['recovered_write_durable_count'])==int(before.split('|')[0])+1
receipt['public_production_recoverability_proven']=False
(E/'recovery-qa.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps(receipt))
