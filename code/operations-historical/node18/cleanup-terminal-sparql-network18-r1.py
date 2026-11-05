"""Finish only the empty labelled network left by this terminal cleanup timeout."""
from pathlib import Path
import hashlib,json,shlex,subprocess,time
R=Path('/ssd/chenkeyi/qwen35-sft-772-20261101');p=R/'formal-native-eval-r1/jobs/qwen35-new772-new-m1-epoch3-fixed-expanded21-20261102-r1/sparql-university__new-m1-e3-fixed-r1/result.json';v=json.loads(p.read_text());assert v['finished_at']and v['failure_phase']=='cleanup'
code=r'''
import subprocess,json
name='q35gpu78newm1e3diag-c853bf6595c34cbc8a177a541409694a_default';identity='c853bf6595c34cbc8a177a541409694a'
v=json.loads(subprocess.check_output(['docker','network','inspect',name],text=True))[0]
assert not v.get('Containers')and v['Labels']['io.harbor.remote-docker.identity']==identity
assert v['Labels']['com.docker.compose.project']==name.removesuffix('_default')
subprocess.run(['docker','network','rm',v['Id']],check=True,capture_output=True,text=True)
print(json.dumps(dict(name=name,id=v['Id'],subnets=v['IPAM']['Config'],containers_before=0,identity=identity,removed=True)))
'''
r=json.loads(subprocess.check_output(['/usr/bin/ssh','-F',str(R/'control-ssh/formal-engine149-r1.conf'),'127.0.0.1','python3 -c '+shlex.quote(code)],text=True,timeout=20));proof=dict(at=time.time(),passed=True,native_trial_already_terminal=True,result_path=str(p),result_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),original_cleanup_error_preserved=True,exact_owned_empty_network_only=r,no_live_container_or_agent_changed=True);q=R/'checks/DIAG150_TERMINAL_SPARQL_EMPTY_NETWORK_CLEANUP_R1.json';assert not q.exists();q.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(r))
