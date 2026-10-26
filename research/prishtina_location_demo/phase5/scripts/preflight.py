"""Phase5 original-checkout preflight and non-sensitive rollback capture."""
from pathlib import Path
import hashlib,json,shutil,subprocess,datetime
ROOT=Path('C:/Projects/FartEstate')
B=ROOT/'research/prishtina_location_demo/phase5'
if (B/'validation/git_preflight.json').exists():
 raise SystemExit('Preflight already frozen; preserve the existing rollback baseline.')
for d in ['reports','processed','validation','scripts','rollback','baseline']:(B/d).mkdir(parents=True,exist_ok=True)
(B/'.gitignore').write_text('processed/\nvalidation/\nrollback/\nbaseline/\n__pycache__/\n',encoding='utf8')
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf8',errors='replace')
status=git('status','--porcelain=v1','--untracked-files=all')
relevant=['src/groundtruth/gazetteers','src/groundtruth/services/normalization.py','src/groundtruth/services/pro_rks_parsing.py','src/groundtruth/services/merrjep_parsing.py','src/groundtruth/processing/parsers/merrjep.py','src/groundtruth/analytics','data/gazetteers','src/groundtruth/models/reference.py']
files={}
for item in relevant:
 p=ROOT/item
 for f in ([p] if p.is_file() else p.rglob('*')):
  if not f.is_file() or '__pycache__' in f.parts or f.suffix not in ['.py','.json','.yaml']:continue
  rel=f.relative_to(ROOT).as_posix(); dest=B/'rollback'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
  files[rel]=hashlib.sha256(f.read_bytes()).hexdigest()
diff=git('diff','--','src','tests','data/gazetteers')
(B/'rollback/preexisting-source.diff').write_text(diff,encoding='utf8')
pre={'head':git('rev-parse','HEAD').strip(),'branch':git('branch','--show-current').strip(),'last_commit':git('log','-1','--format=%H %s').strip(),'status':status.splitlines(),'diff_stat':git('diff','--stat'),'relevant_preexisting_diff_sha256':hashlib.sha256(diff.encode()).hexdigest(),'source_hashes':files,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_checkout':str(ROOT),'strategy':'Isolated managed worktree; preserve original dirty checkout and background MerrJep runtime. No database writes.'}
(B/'validation/git_preflight.json').write_text(json.dumps(pre,indent=2)+'\n',encoding='utf8')
(B/'validation/source_fingerprints.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf8')
print(json.dumps({'head':pre['head'],'branch':pre['branch'],'preserved_files':len(files),'dirty_paths':len(pre['status'])}))
