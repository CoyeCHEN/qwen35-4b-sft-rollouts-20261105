"""Read-only HTTP GET through one live explicit-IPAM environment; Bash is native."""
from pathlib import Path
import hashlib,json,shlex,subprocess,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');E=R/'formal-native-eval-r1'
p=E/'manifests/PRE_MODEL_ENV_RECOVERY_new-m1-e3-diag_ACTUAL_TRIALS_R1.json';actual=json.loads(p.read_text());trial=actual['trials'][0];d=Path(trial['trials_dir'])/trial['trial_name'];files=list(d.glob('remote-docker-*.jsonl'));assert len(files)==1;identity=files[0].stem.removeprefix('remote-docker-')
code=r'''
import subprocess,json,time
identity=IDENTITY
ids=subprocess.check_output(['docker','ps','--filter','label=io.harbor.remote-docker.identity='+identity,'-q'],text=True).split();assert len(ids)==1
v=json.loads(subprocess.check_output(['docker','inspect',ids[0]],text=True))[0]
assert v['Config']['Labels']['io.harbor.remote-docker.identity']==identity
assert any(x['IPAddress'].startswith('10.247.')for x in v['NetworkSettings']['Networks'].values())
probe="exec 3<>/dev/tcp/172.17.0.1/18303\nprintf 'GET /model_info HTTP/1.0\\r\\nHost: 172.17.0.1\\r\\nConnection: close\\r\\n\\r\\n' >&3\ncat <&3"
r=subprocess.run(['docker','exec',ids[0],'bash','-c',probe],capture_output=True,text=True,timeout=15)
assert r.returncode==0,r.stderr
text=r.stdout.replace('\r\n','\n');header,_,body=text.partition('\n\n');assert ' 200 OK'in header.splitlines()[0]
info=json.loads(body)
print(json.dumps(dict(at=time.time(),identity=identity,container=ids[0],networks={k:dict(ip=x['IPAddress'],gateway=x['Gateway'])for k,x in v['NetworkSettings']['Networks'].items()},model_info=info)))
'''.replace('IDENTITY',repr(identity))
value=json.loads(subprocess.check_output(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(code)],text=True,timeout=25))
assert value['model_info']['weight_version']=='2e02fec581cbb3c802cd1e0e80ac2c9568bead3a9002338f4d661ea6ac94053d'
proof=dict(passed=True,at=time.time(),trial_path=str(d),actual_model_generation_calls=0,read_only_probe=True,no_task_workspace_or_agent_observation_changed=True,actual_endpoint=value,earlier_nop_failure='regex task does not provide python3; exit127 was dependency of probe only; no network failure was established',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
q=R/'checks/EVALUATION_EXPLICIT_IPAM_MODEL_ROUTE_ACCEPTANCE_R3.json';assert not q.exists();q.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(passed=True,identity=identity,model_generation_calls=0,networks=value['networks'])))
