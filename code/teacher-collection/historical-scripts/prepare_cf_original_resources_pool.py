"""Finite CF500 environment preparation as verified public archives arrive.

One environment-preparation worker, no Harbor agent/model scheduling. Existing
native image import and TaskConfig resource handling own each actual check.
"""
from collections import Counter
import json,os,shlex,shutil,subprocess,sys,time
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
for k in ['DEEPSEEK_API_KEY','GH_TOKEN']:os.environ.pop(k,None)
os.environ['DOCKER_HOST']='ssh://chenkeyi@127.0.0.1:5102';os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
rows={x['task_id']:x for x in map(json.loads,(R/'manifests/CALIBFORGE_500_TASKS.jsonl').open())};assert len(rows)==500
previous={}
for dirname in ['cf-environments-v2','cf-environments-recheck-r3','cf-environments-oci-r4','cf-environments-oci-r5']:
 for p in (R/'checks'/dirname).glob('*.json'):
  item=json.loads(p.read_text())
  if item.get('status')=='IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED' and item['task_id'] in rows:
   previous[item['task_id']]=item['image_id']
state_path=R/'checks/cf-original-resources-pool-preparation.json'
if state_path.exists():raise FileExistsError('Existing exact worker needs observation, not duplicate dispatch')
pending=set(rows);observed={}
while pending:
 if shutil.disk_usage(R).free<100*1024**3:
  state_path.write_text(json.dumps(dict(status='WAITING_FOR_100GIB_DISK_HEADROOM',planned_tasks=500,remaining_tasks=len(pending),model_calls=0),indent=2));break
 code='''from pathlib import Path
import json
r=Path("/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/registry")
ready={}
for name in ["tasks","tasks-local-skopeo-r1"]:
 for p in (r/name).glob("*/cache.json"):
  x=json.loads(p.read_text())
  if x.get("status")=="PINNED_PUBLIC_IMAGE_ARCHIVE_READY":ready[x["task_id"]]=x["pinned"]
print(json.dumps(ready))'''
 try:
  reply=subprocess.run(['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false',
    'chenkeyi@180.163.192.17','python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True,timeout=10)
  available=json.loads(reply.stdout)
 except (OSError,ValueError,subprocess.SubprocessError) as error:
  print(json.dumps(dict(status='PUBLIC_CACHE_INVENTORY_TEMPORARILY_UNOBSERVED',error_type=type(error).__name__)),flush=True);time.sleep(30);continue
 ready=[]
 for ident in sorted(pending):
  receipt=R/'checks/cf-environments-oci-r5'/(ident+'.json')
  if receipt.exists():
   observed[ident]=json.loads(receipt.read_text())['status']
  elif ident in previous or ident in available:
   if ident in available:
    source=json.loads((R/'checks/cf-public-image-identities'/(ident+'.json')).read_text());assert available[ident]==source['pinned']
   ready.append(ident)
 for ident in observed:pending.discard(ident)
 for ident in ready:
  subprocess.run([sys.executable,str(R/'scripts/prepare_cf_native_oci_images_r5.py'),'--task-id',ident],check=False)
  p=R/'checks/cf-environments-oci-r5'/(ident+'.json')
  if not p.exists():raise RuntimeError('Native preparation returned without an immutable receipt; inspect before replay')
  observed[ident]=json.loads(p.read_text())['status'];pending.discard(ident)
  state_path.write_text(json.dumps(dict(status='PREPARING_ORIGINAL_RESOURCE_ENVIRONMENTS',planned_tasks=500,
    observed_tasks=len(observed),remaining_tasks=len(pending),counts=dict(Counter(observed.values())),model_calls=0,teacher_attempts=0,
    source='Native TaskConfig normalized CPU/RAM; original task files and verifier unchanged'),indent=2))
 if pending:time.sleep(30)
else:
 state_path.write_text(json.dumps(dict(status='ALL_500_ENVIRONMENT_CHECKS_TERMINAL_VERIFIER_PENDING',planned_tasks=500,
  observed_tasks=500,counts=dict(Counter(observed.values())),model_calls=0,teacher_attempts=0),indent=2))
