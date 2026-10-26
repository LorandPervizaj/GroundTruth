"""Validate runtime files, dependency inventory, privacy and public-baseline bytes."""
from pathlib import Path
import subprocess,json,hashlib
E=Path('C:/Projects/FartEstate/release/readiness/evidence');identity=json.loads((E/'release-identity.json').read_text())
image=identity['image_config_id']
code='''
from pathlib import Path
import os,json,hashlib,gzip,importlib.metadata
root=Path('/app')
required=['web/static/charts.js','src/groundtruth/gazetteers/market_graph.py','alembic','data/gazetteers/market_relationships.json']
assert all((root/p).exists()for p in required)
forbidden=['.env','.git','security','research','release','data/raw','backups']
assert not any((root/p).exists()for p in forbidden)
assert os.getuid()!=0
hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()for folder in ['reports/generated/lookup_cache','data/api']for p in(root/folder).rglob('*')if p.is_file()}
from groundtruth.release import verify_release_artifacts
verified=verify_release_artifacts()
from groundtruth.services.public_payload import FORBIDDEN_LISTING_FIELD_KEYS
comparables={}
for p in(root/'reports/generated/lookup_cache').glob('*comparables.json.gz'):
 payload=json.loads(gzip.open(p,'rt').read());rows=payload['data']
 assert all(not FORBIDDEN_LISTING_FIELD_KEYS.intersection(r)for r in rows)
 comparables[p.name]=len(rows)
from groundtruth.cli import app
print(json.dumps({'uid':os.getuid(),'required_paths':required,'forbidden_paths_absent':forbidden,'verification':verified,'artifact_hashes':hashes,'comparables_rows_checked':comparables,'dependency_versions':{p:importlib.metadata.version(p)for p in ['brotli','certifi','pillow','fastapi','starlette','uvicorn']},'cli_import':True}))
'''
result=subprocess.run(['docker','run','--rm','--network','none','--read-only','--entrypoint','/app/.venv/bin/python',image,'-c',code],capture_output=True,text=True)
assert result.returncode==0,result.stderr
receipt=json.loads(result.stdout);receipt['image_digest']=identity['image_manifest_digest']
reference=json.loads((E/'public-baseline-freeze.json').read_text())['after']
assert all(reference[p]==h for p,h in receipt['artifact_hashes'].items())
receipt['production_public_artifact_bytes_equal']=True
(E/'image-inspection.json').write_text(json.dumps(receipt,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in receipt.items()if k!='artifact_hashes'}))
