"""Prepare one already-selected earlier task; the sole controller dispatches it."""
import datetime,fcntl,hashlib,json,os,shlex,subprocess,sys
from pathlib import Path
R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
ID='task_009816_25751511'
REMOTE="""import pathlib,json,hashlib,subprocess
from inspect_cold_oci_r1 import sha_file
r=pathlib.Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
s=pathlib.Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029')
ident='task_009816_25751511';h='unix://'+str(s/'engine17-r1/socket/docker.sock')
p=s/'buildkit-rootless-r2/archives'/ident/'client-proxy-r3/build.json';x=json.loads(p.read_text())
assert x['status']=='ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' and x['all_manifest_config_layer_hashes_verified']
assert x['native_manifest_digest']=='sha256:54d7867c87161f2bf1f03ec7811a8033591c12fcb29458c645b02146886db90f'
assert x['source_context']['source_manifest_sha256']=='35628e5d83b46384f5d53abb4b2603c7bba1e807ea04e718653a59df2726c6fd'
archive=pathlib.Path(x['archive']);assert sha_file(archive)==x['archive_sha256']
q=subprocess.run(['docker','--host',h,'info','--format','{{.ID}}'],capture_output=True,text=True,check=True)
assert q.stdout.strip()=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
q=subprocess.run(['docker','--host',h,'image','inspect',x['native_manifest_digest']],capture_output=True,text=True)
if q.returncode:
 with (s/'engine17-r1/logs/earlier-original-canary-image-load-r4.log').open('x') as log:
  subprocess.run(['docker','--host',h,'image','load','--input',str(archive)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
subprocess.run([sys.executable,str(r/'scripts/accept_private_ssd_engine17_resources_r4.py')],check=True)
print('RESULT_PROOF '+(r/'checks/private-ssd-engine17-original-resource-acceptance-r4.json').read_text().replace(chr(10),' '))
"""
def freeze(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2)
def main():
 lock=(R/'checks/prepare-earlier-original-canary-r4.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 import run_collection_stream_r4 as c
 assert not c.attempt_counts().get(ID,0)
 assert ID not in json.loads((R/'campaign-state.json').read_text())['active_task_pipelines']
 code='import sys;sys.path.insert(0,"/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029/scripts");'+REMOTE
 ssh=['ssh','-S','/home/chenkeyi/.ssh/cf17-20261028.sock','-oBatchMode=yes','-oProxyCommand=false','chenkeyi@180.163.192.17']
 py='/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-length-lf-audit-20261023/.venv/bin/python'
 q=subprocess.run([*ssh,shlex.join([py,'-c',code])],capture_output=True,text=True,timeout=1500)
 log=R/'logs/earlier-original-canary-resource-r4.log'
 with log.open('x') as f:f.write(q.stdout+'\n'+q.stderr)
 q.check_returncode()
 value=json.loads(next(x.removeprefix('RESULT_PROOF ') for x in q.stdout.splitlines() if x.startswith('RESULT_PROOF ')))
 assert value['status']=='ORIGINAL_TASK_RESOURCES_INITIAL_STATE_AND_NETWORK_ACCEPTED_NATIVE_CLI_NOP_PENDING' and value['cleanup_confirmed']
 freeze(R/'checks/private-ssd-engine17-original-resource-acceptance-r4.json',value)
 for name in ['accept_private17_native_task149_r4.py','register_private17_canary149_r4.py']:
  subprocess.run([sys.executable,str(R/'scripts'/name)],check=True)
 print(json.dumps(dict(status='ORIGINAL_EARLIER_TASK_ENVIRONMENT_REGISTERED_EXISTING_CONTROLLER',task_id=ID,teacher_dispatches_by_preparer=0)),flush=True)
if __name__=='__main__':
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']:os.environ.pop(key,None)
 os.environ['PATH']=str(R/'client-bin-v2')+':'+os.environ['PATH']
 os.environ['SSH_AUTH_SOCK']='/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
 main()
