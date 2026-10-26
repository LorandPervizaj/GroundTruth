"""Commit only reviewed RC files and build from a Git archive, never a dirty tree."""
from pathlib import Path
import subprocess,json,hashlib,shutil,os,datetime
O=Path('C:/Projects/FartEstate');R=Path('C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate');P=O/'release/readiness';E=P/'evidence'
def git(*args):return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
assert git('branch','--show-current')=='codex/metrik-production-rc-20261026'
assert not git('diff','--cached','--name-only')
dest=R/'release/readiness';dest.mkdir(parents=True,exist_ok=True)
for p in P.glob('*.py'):shutil.copy2(p,dest/p.name)
shutil.copy2(P/'.gitignore',dest/'.gitignore')
paths=git('diff','--name-only').splitlines()+['tests/test_release_gazetteer_bootstrap.py']+[p.relative_to(R).as_posix()for p in dest.iterdir()if p.is_file()]
paths=sorted(set(paths))
allowed=('.dockerignore','uv.lock','scripts/load_gazetteers.py','src/groundtruth/scrapers/harta_contract.py','tests/test_web_runtime_imports.py','tests/test_release_gazetteer_bootstrap.py','tests/e2e/test_public_site.py','web/','data/api/','reports/generated/lookup_cache/','release/readiness/')
paths=sorted(set(paths+['tests/test_web_runtime_imports.py']))
assert all(p.startswith(allowed)for p in paths)
assert not any('/evidence/'in p for p in paths)
subprocess.run(['git','add','--',*paths],cwd=R,check=True,capture_output=True)
subprocess.run(['git','diff','--cached','--check','--','.dockerignore','scripts','tests','release','web'],cwd=R,check=True,capture_output=True)
subprocess.run(['git','commit','-m','Freeze Metrik release candidate with production public baseline and safe reference bootstrap'],cwd=R,check=True,capture_output=True)
sha=git('rev-parse','HEAD');assert not git('status','--porcelain=v1')
archive=E/'source-context.tar'
with archive.open('wb')as f:subprocess.run(['git','archive','--format=tar',sha],cwd=R,stdout=f,check=True)
tag='metrik-api:rc-'+sha[:12]
cmd=['docker','buildx','build','--load','--provenance=false','--metadata-file',str(E/'build-metadata.json'),'--label','org.opencontainers.image.revision='+sha,'-t',tag,'-']
identity={'git_sha':sha,'branch':git('branch','--show-current'),'tag':tag,'archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'build_command':cmd,'source_clean':True,'built_from':'git archive '+sha,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pushed':False}
(E/'release-identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8');print(json.dumps(identity),flush=True)
with archive.open('rb')as source,(E/'image-build.log').open('w',encoding='utf8')as log:
 result=subprocess.run(cmd,cwd=R,stdin=source,stdout=log,stderr=subprocess.STDOUT)
identity['build_exit_code']=result.returncode
if result.returncode==0:
 meta=json.loads((E/'build-metadata.json').read_text());identity['image_manifest_digest']=meta.get('containerimage.digest');identity['image_config_id']=git_image=json.loads(subprocess.check_output(['docker','image','inspect',tag],text=True))[0]['Id']
(E/'release-identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8');print(json.dumps(identity),flush=True)
raise SystemExit(result.returncode)
