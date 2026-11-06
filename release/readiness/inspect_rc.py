"""Read-only release preflight and redacted current Azure evidence."""
from pathlib import Path
import datetime,hashlib,json,subprocess
ORIG=Path('C:/Projects/FartEstate')
RC=Path('C:/Users/lorandp/.codex/worktrees/metrik-release-candidate/FartEstate')
OUT=ORIG/'release/readiness';E=OUT/'evidence';E.mkdir(parents=True,exist_ok=True)
def run(args,cwd=ORIG):
 p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
 if p.returncode:raise RuntimeError(f'{args[:3]} exit {p.returncode}: {p.stderr[-500:]}')
 return p.stdout
def save(name,data):(E/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
if not (E/'preflight.json').exists():
 tracked=run(['git','diff','--name-only']).splitlines();untracked=run(['git','ls-files','--others','--exclude-standard']).splitlines()
 source=[p for p in run(['git','ls-files','src','web','data/gazetteers','Dockerfile','uv.lock','pyproject.toml']).splitlines()if(ORIG/p).is_file()]
 save('preflight.json',{'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_head':run(['git','rev-parse','HEAD']).strip(),'original_branch':run(['git','branch','--show-current']).strip(),'tracked_changes':tracked,'untracked_paths':untracked,'staged_paths':run(['git','diff','--cached','--name-only']).splitlines(),'source_hashes':{p:sha(ORIG/p)for p in source},'phase5_head':run(['git','rev-parse','HEAD'],RC).strip(),'unrelated_changes_policy':'Preserve every original-checkout change; release source starts at committed Phase5, no blanket staging.'})
app=json.loads(run(['az.cmd','containerapp','show','-n','ca-metrik-api','-g','rg-metrik-beta-eus2','-o','json']))
p=app['properties'];config=p['configuration'];template=p['template']
safe={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'id':app['id'],'location':app['location'],'environment_id':p.get('environmentId'),'latest_revision':p.get('latestRevisionName'),'latest_ready_revision':p.get('latestReadyRevisionName'),'revision_mode':config.get('activeRevisionsMode'),'ingress':config.get('ingress'),'volumes':template.get('volumes'),'scale':template.get('scale'),'containers':[]}
allowed={'APP_ENV','API_DOCS_ENABLED','API_REQUIRE_LOOKUP_CACHE','PRODUCT_WRITE_BACKEND','RUN_MIGRATIONS_ON_START','PUBLIC_BASE_URL','TRUSTED_HOSTS','REPORTS_GENERATED_DIR','PGDATA','POSTGRES_DB','ALERTS_SIGNUP_ENABLED','VALUATION_PUBLIC_ENABLED','API_RATE_LIMIT_ENABLED'}
for c in template['containers']:
 safe['containers'].append({'name':c['name'],'image':c['image'],'mounts':c.get('volumeMounts'),'probes':c.get('probes'),'env':[{'name':v['name'],**({'secretRef':v['secretRef']}if v.get('secretRef')else{'value':v.get('value')}if v['name']in allowed else{'value':'[not collected]'})}for v in c.get('env',[])]})
save('azure-current.json',safe)
revs=json.loads(run(['az.cmd','containerapp','revision','list','-n','ca-metrik-api','-g','rg-metrik-beta-eus2','-o','json']))
save('azure-revisions.json',[{'name':r['name'],'active':r['properties'].get('active'),'health':r['properties'].get('healthState'),'running':r['properties'].get('runningState'),'traffic':r['properties'].get('trafficWeight'),'created':r['properties'].get('createdTime'),'images':[c['image']for c in r['properties']['template']['containers']]}for r in revs])
image=next(c['image']for c in template['containers']if c['name']=='metrik-api');tag=image.split('/')[-1]
digest=json.loads(run(['az.cmd','acr','repository','show','-n','acrmetrikbetalgy2mu','--image',tag,'-o','json']))
save('azure-current-image.json',{'tag':image,'digest':digest.get('digest'),'created':digest.get('createdTime'),'updated':digest.get('lastUpdateTime'),'attributes':digest.get('changeableAttributes')})
print(json.dumps({'saved':str(E),'revision':safe['latest_ready_revision'],'volumes':safe['volumes'],'image':image,'digest':digest.get('digest')}))
