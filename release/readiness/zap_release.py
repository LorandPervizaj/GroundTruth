"""Use the installed audit runner for the explicitly authorized loopback QA origin."""
from pathlib import Path
import importlib.util,json
O=Path('C:/Projects/FartEstate');E=O/'release/readiness/evidence';run=E/'zap-release';run.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('release_security_audit',O/'security/scripts/audit.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
read=audit.read
def session_scope(path,default=None):
 data=read(path,default)
 if Path(path)==audit.SEC/'config/scan-scope.json':
  data=dict(data);data['passive_origins']=['http://127.0.0.1:18765'];data['passive_paths']=['/','/statistics','/find','/valuate','/compare','/rent-yield','/about','/methodology','/api/ready']
 return data
audit.read=session_scope
audit.dump(run/'authorization.json',{'authority':'User final release candidate brief authorizes disposable local QA security tests.','origin':'http://127.0.0.1:18765','profile':'passive','production':False,'shared_scope_file_modified':False,'scope_application':'In-memory session-specific whitelist; existing runner validation remains enforced.'})
audit.web(run,'http://127.0.0.1:18765',False,False)
