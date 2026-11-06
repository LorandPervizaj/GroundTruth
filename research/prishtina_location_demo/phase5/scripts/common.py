from pathlib import Path
import json,csv,gzip,hashlib,datetime,math
ROOT=Path('C:/Users/lorandp/.codex/worktrees/prishtina-phase5/FartEstate')
ORIGINAL=Path('C:/Projects/FartEstate')
B=ORIGINAL/'research/prishtina_location_demo/phase5'
P=ORIGINAL/'research/prishtina_location_demo/phase3'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str,allow_nan=False)+'\n',encoding='utf8')
def rows(p):
 with gzip.open(p,'rt',encoding='utf8') as f:
  for line in f:yield json.loads(line)
def csvout(name,rs,fields=None):
 rs=list(rs);fields=fields or list(dict.fromkeys(k for r in rs for k in r)) or ['record_id','reason']
 with (B/name).open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for r in rs:writer.writerow({k:json.dumps(v,ensure_ascii=False,default=str) if isinstance(v,(list,dict,tuple)) else v for k,v in r.items() if k in fields})
def digest(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def connect():
 import psycopg
 from dotenv import dotenv_values
 from sqlalchemy.engine import make_url
 u=make_url(dotenv_values(ORIGINAL/'.env')['DATABASE_URL'])
 assert u.host in ['localhost','127.0.0.1'] and u.port==15432 and u.database=='rema'
 return psycopg.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,password=u.password,connect_timeout=8,options='-c default_transaction_read_only=on -c statement_timeout=180000 -c lock_timeout=5000 -c application_name=phase5_readonly')
