"""One finite environment-only recheck of frozen CF failures; preserve all first receipts."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
r=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
os.environ['DOCKER_HOST']='ssh://chenkeyi@127.0.0.1:5102'
os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
os.environ['PATH']=str(r/'client-bin-v2')+':'+os.environ['PATH']
failures=[]
for p in sorted((r/'checks/cf-environments-v2').glob('*.json')):
 x=json.loads(p.read_text())
 if x['status']=='ENVIRONMENT_PREPARATION_FAILED':
  failures.append(dict(task_id=x['task_id'],previous_receipt=str(p),previous_receipt_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
plan=r/'checks/CF_ENVIRONMENT_RECHECK_R3_PLAN.json'
if plan.exists():raise FileExistsError('One finite recheck was already registered')
plan.write_text(json.dumps(dict(tasks=failures,model_calls=0,teacher_attempts=0,reason='Inspected public pull/TLS timeouts and basic setup command timeouts; unchanged tasks and immutable image identities'),indent=2))
for item in failures:
 x=subprocess.run([sys.executable,str(r/'scripts/prepare_cf_failed_rechecks.py'),'--task-id',item['task_id']])
 print(json.dumps(dict(task_id=item['task_id'],returncode=x.returncode)),flush=True)
