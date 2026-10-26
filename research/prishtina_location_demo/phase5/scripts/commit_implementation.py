"""Focused local Phase5 commit, preserving the original dirty checkout."""
from common import *
import shutil,subprocess
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf8',errors='replace')
assert ROOT.resolve()!=ORIGINAL.resolve()
assert git('branch','--show-current').strip()=='codex/prishtina-phase5'
assert read(B/'validation/artifact_checks.json')['status']=='passed'
assert subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,'Unexpected already-staged files; preserve them and inspect.'
dest=ROOT/'research/prishtina_location_demo/phase5'
for folder,pattern in [('reports','*.md'),('scripts','*.py')]:
 (dest/folder).mkdir(parents=True,exist_ok=True)
 for p in (B/folder).glob(pattern):shutil.copy2(p,dest/folder/p.name)
shutil.copy2(B/'.gitignore',dest/'.gitignore')
modified=git('diff','--name-only').splitlines()
new=['data/gazetteers/market_relationships.json','src/groundtruth/gazetteers/market_graph.py','src/groundtruth/analytics/market_hierarchy.py','tests/test_phase5_locations.py','tests/fixtures/phase5/location_examples.json']
paths=sorted(set(modified+new+[p.relative_to(ROOT).as_posix()for p in dest.rglob('*')if p.is_file()]))
allowed=('data/gazetteers/','src/groundtruth/gazetteers/','src/groundtruth/services/normalization.py','src/groundtruth/services/pro_rks_parsing.py','src/groundtruth/services/merrjep_parsing.py','src/groundtruth/processing/confidence.py','src/groundtruth/analytics/market_hierarchy.py','tests/test_phase5_locations.py','tests/test_location_resolver.py','tests/test_normalizers.py','tests/fixtures/phase5/','research/prishtina_location_demo/phase5/reports/','research/prishtina_location_demo/phase5/scripts/','research/prishtina_location_demo/phase5/.gitignore')
assert all(p.startswith(allowed) for p in paths)
assert not any('/'+private+'/' in p for p in paths for private in ['processed','baseline','rollback','validation'])
subprocess.run(['git','add','--',*paths],cwd=ROOT,check=True)
staged=git('diff','--cached','--name-only').splitlines();assert set(staged)==set(paths)
subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
for filename,args in [('phase5-implementation.patch',['diff','--cached','--binary']),('phase5-reverse.patch',['diff','--cached','--binary','-R'])]:
 data=subprocess.check_output(['git',*args],cwd=ROOT);(B/'rollback'/filename).write_bytes(data)
commit=subprocess.run(['git','commit','-m','Implement Prishtina market hierarchy and context-aware location resolution'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
result={'original_head':read(B/'validation/git_preflight.json')['head'],'original_branch':read(B/'validation/git_preflight.json')['branch'],'implementation_branch':git('branch','--show-current').strip(),'implementation_checkout':str(ROOT),'committed':commit.returncode==0,'implementation_commit':git('rev-parse','HEAD').strip() if commit.returncode==0 else None,'commit_output':commit.stdout[-2500:],'commit_error':commit.stderr[-2000:]if commit.returncode else None,'authored_paths':staged,'implementation_status':git('status','--porcelain=v1').splitlines(),'original_branch_after':subprocess.check_output(['git','branch','--show-current'],cwd=ORIGINAL,text=True).strip(),'original_head_after':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ORIGINAL,text=True).strip(),'remote_push':False,'patch_sha256':digest(B/'rollback/phase5-implementation.patch'),'reverse_patch_sha256':digest(B/'rollback/phase5-reverse.patch')}
write(B/'validation/git_final.json',result)
print(json.dumps(result,ensure_ascii=True))
