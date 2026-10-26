"""Recover only the owned ephemeral test fixture after the init-server race."""
from pathlib import Path
import subprocess,json,time
E=Path('C:/Projects/FartEstate/release/readiness/evidence');db='metrik-rc-testdb-20261026'
s=json.loads(subprocess.check_output(['docker','inspect',db],text=True))[0]
assert s['Config']['Labels'].get('metrik.rc')=='20261026'
if not s['State']['Running']:subprocess.run(['docker','start',db],check=True,capture_output=True)
for _ in range(45):
 if subprocess.run(['docker','exec',db,'pg_isready','-h','127.0.0.1','-U','groundtruth_test','-d','groundtruth_test'],capture_output=True).returncode==0:break
 time.sleep(1)
else:raise RuntimeError('Owned QA database did not finish TCP initialization')
result=subprocess.run(['docker','exec','-i',db,'pg_restore','-U','groundtruth_test','-d','groundtruth_test','--clean','--if-exists','--no-owner','--exit-on-error'],input=(E/'disposable-qa.dump').read_bytes(),capture_output=True)
assert result.returncode==0,result.stderr.decode()
print('Owned QA fixture restored after waiting for final TCP listener; no production access.')
