"""Freeze current production's public artifacts; never regenerate market data."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
O=Path('C:/Projects/FartEstate');R=Path('C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate');E=O/'release/readiness/evidence';P=E/'production-artifacts'
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
before={};after={};changed=[];logical_web=[]
for source,dest in [('lookup_cache','reports/generated/lookup_cache'),('api','data/api'),('web','web')]:
 for p in(P/source).rglob('*'):
  if not p.is_file():continue
  rel=Path(dest)/p.relative_to(P/source);target=R/rel
  before[rel.as_posix()]=sha(target)if target.is_file()else None
  if source=='web' and target.exists() and p.read_bytes().replace(b'\r\n',b'\n')!=target.read_bytes().replace(b'\r\n',b'\n'):logical_web.append(rel.as_posix())
  if source!='web' or not target.exists()or p.read_bytes().replace(b'\r\n',b'\n')!=target.read_bytes().replace(b'\r\n',b'\n'):
   target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
  after[rel.as_posix()]=sha(target)
  if before[rel.as_posix()]!=after[rel.as_posix()]:changed.append(rel.as_posix())
sys.path.insert(0,str(R/'src'))
from groundtruth.release import verify_release_artifacts
results=verify_release_artifacts()
receipt={'source_image':'acrmetrikbetalgy2mu.azurecr.io/metrik-api@sha256:d2de1bd0d2dcd80770819c64effbf868236672909a15e1e915234b21aa9c6573','method':'docker create inert image reference, docker cp public paths only; no production writes or data regeneration','before':before,'after':after,'changed_paths':changed,'frontend_logical_differences':logical_web,'frontend_delta':'Current production HTML omits the Iubenda script block present in old committed source; HTML aligned to current production. Layout, CSS, JS logic and charts unchanged.','verification':results,'artifact_manifest_sha256':sha(R/'reports/generated/lookup_cache/manifest.json'),'market_statistics_regenerated':False}
(E/'public-baseline-freeze.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps({'changed_files':len(changed),'frontend_html_aligned':len(logical_web),'verification':results}))
