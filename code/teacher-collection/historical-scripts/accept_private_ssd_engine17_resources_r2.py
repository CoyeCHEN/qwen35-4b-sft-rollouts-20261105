"""Zero-model original Task resource, initial-state and network acceptance."""
import datetime, hashlib, json, os, subprocess
from pathlib import Path
R=Path('/home/chenkeyi/workspace/RSI/runtime-evidence/qwen35-new-cf500-tmax500-20261029')
S=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/engine17-r1')
HOST='unix://'+str(S/'socket/docker.sock')
ID='task_007016_4f9de434'
NAME='rsi-ssd17-original-resource-probe-r2'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,timeout=180): return subprocess.run(args,text=True,capture_output=True,timeout=timeout)
def docker(*args,timeout=180): return run(['docker','--host',HOST,*args],timeout)
def checked(reply):
 if reply.returncode: raise RuntimeError(reply.stderr[-1500:] or reply.stdout[-1500:])
 return reply.stdout
def main():
 for key in ['DEEPSEEK_API_KEY','GH_TOKEN','OPENAI_API_KEY']: os.environ.pop(key,None)
 plan=R/'manifests/TMAX_REMAINING_INITIAL_SSD17_R7.json'
 row=next(x for x in json.loads(plan.read_text())['tasks'] if x['task_id']==ID)
 receipt=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/buildkit-rootless-r2/archives')/ID/'client-proxy-r3/build.json'
 built=json.loads(receipt.read_text());image=built['native_manifest_digest']
 test=Path('/ssd/chenkeyi/qwen35-new-cf500-tmax500-20261029/trusted-tmax-initial-ssd17-r7')/ID/'test_initial_state.py'
 assert sha(test)==row['initial_test_sha256']
 hidden=S/'logs/trusted-initial/test_initial_state.py';hidden.parent.mkdir(exist_ok=True);hidden.write_bytes(test.read_bytes());hidden.chmod(0o444)
 engine=json.loads(checked(docker('info','--format','{{json .}}')))
 assert engine['ID']=='59c8ba22-0aa4-4aed-bc43-4e1b5989fa22'
 resources=row['original_resources']; command=row['native_startup_override']['services']['main']['command'];command=[*command[:-1],command[-1].replace('$$','$')]
 out=dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),task_id=ID,node='17',engine_id=engine['ID'],model_calls=0,
  task_resources=resources,manifest=str(plan),manifest_sha256=sha(plan),original_build_receipt=str(receipt),original_build_receipt_sha256=sha(receipt),
  image_id=image,initial_test_sha256=sha(test),shared_daemon_configuration_changes=0,status='ENV_FAILED')
 try:
  checked(docker('create','--name',NAME,'--runtime','runc','--label','rsi.campaign='+R.name,
   '--cpus',str(resources['cpus']),'--memory',str(resources['memory_mb']*1024**2),'--workdir','/home/user','--env','HOME=/home/user',
   '--mount','type=bind,src=/campaign-logs/trusted-initial/test_initial_state.py,dst=/trusted-preparation/test_initial_state.py,readonly',
   '--entrypoint','/bin/bash',image,*command[1:]))
  inspected=json.loads(checked(docker('inspect',NAME)))[0]; actual=inspected['HostConfig'];out['host_config']=dict(memory=actual['Memory'],nano_cpus=actual['NanoCpus'],privileged=actual['Privileged'],device_requests=actual.get('DeviceRequests'),log_config=actual['LogConfig'])
  assert actual['Memory']==resources['memory_mb']*1024**2 and actual['NanoCpus']==round(resources['cpus']*1e9) and not actual['Privileged'] and not actual.get('DeviceRequests')
  checked(docker('start',NAME))
  code="""import json, pathlib, socket, ssl
p=pathlib.Path('/sys/fs/cgroup')
cpu=(p/'cpu.max').read_text().strip();memory=(p/'memory.max').read_text().strip()
assert cpu.split()[0]!='max' and int(cpu.split()[0])/int(cpu.split()[1])==1
assert int(memory)==2147483648
assert not pathlib.Path('/dev/nvidia0').exists()
with socket.create_connection(('api.deepseek.com',443),timeout=20) as sock:
 with ssl.create_default_context().wrap_socket(sock,server_hostname='api.deepseek.com') as secure: tls=secure.version()
print(json.dumps(dict(cpu_max=cpu,memory_max=memory,direct_deepseek_tls=tls,gpu_device_present=False)))
"""
  out['cgroup_and_direct_network']=json.loads(checked(docker('exec',NAME,'python3','-c',code)))
  q=docker('exec','--workdir','/home/user','--env','HOME=/home/user',NAME,'bash','-lc','set -eu; pwd -P; id; test "$HOME" = /home/user; test "$(pwd -P)" = /home/user; test -w .; test ! -e /tests; python3 -m pytest -q /trusted-preparation/test_initial_state.py')
  for kind,text in [('stdout',q.stdout),('stderr',q.stderr)]:
   p=S/('original-initial-state-r2-'+kind+'.txt');p.write_text(text);out['initial_'+kind]=dict(path=str(p),sha256=sha(p))
  out['initial_state_returncode']=q.returncode; checked(q)
  out.update(status='ORIGINAL_TASK_RESOURCES_INITIAL_STATE_AND_NETWORK_ACCEPTED_NATIVE_CLI_NOP_PENDING',environment_and_storage_accepted=False)
 except Exception as error: out.update(error_type=type(error).__name__,reason=str(error)[:1800])
 finally:
  q=docker('rm','-f',NAME);out['cleanup_confirmed']=q.returncode==0 or 'No such container' in q.stderr
  p=R/'checks/private-ssd-engine17-original-resource-acceptance-r2.json'
  with p.open('x') as f: json.dump(out,f,indent=2)
  print(json.dumps({k:v for k,v in out.items() if k in ['status','engine_id','cgroup_and_direct_network','initial_state_returncode','cleanup_confirmed','reason']}),flush=True)
if __name__=='__main__': main()
