"""Bound the already running orphan CLI; never start another model attempt."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new772-tb21-20261101')
CID='019df609b188'
IDENTITY='8326db5f630143ee9fb93dad9c01c6cd'
PID=552
TICKS='219688827'
# The original in-memory Harbor phase-start timestamp was lost. This is the
# preceding completed setup/version probe, not a new 3h budget from recovery.
DEADLINE=1793572741.155354
CODE=r'''
from pathlib import Path
import json,os,signal,sys
p=Path('/proc/552/stat');alive=False
if p.exists():
 raw=p.read_text();alive=raw.rsplit(')',1)[1].split()[19]=='219688827'
argv=Path('/proc/552/cmdline').read_bytes().split(bytes([0]))if alive else []
if alive and not any(x.endswith(b'/open-harness')for x in argv[:2]):raise ValueError('CLI command identity changed')
action=sys.argv[1]
if alive and action!='observe':os.kill(552,{'interrupt':signal.SIGINT,'terminate':signal.SIGTERM,'kill':signal.SIGKILL}[action])
q=Path('/logs/agent/open-harness.complete.json')
print(json.dumps(dict(alive_same_original_cli=alive,completion=json.loads(q.read_text())if q.exists()else None)))
'''


def inspect_cli(action='observe'):
    value=json.loads(subprocess.check_output(['docker','inspect',CID],text=True))[0]
    if value['Config']['Labels']['io.harbor.remote-docker.identity']!=IDENTITY:
        raise ValueError('Original container identity changed')
    result=subprocess.run(['docker','exec',CID,'/harbor/agent-runtime/harbor-open-harness-venv/bin/python',
                           '-c',CODE,action],capture_output=True,text=True,timeout=20)
    result.check_returncode()
    return json.loads(result.stdout)


def save(path,value):
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,indent=2)+'\n')
    temp.replace(path)


def main():
    output=R/'recovery/e3-controller-oom-20261102-r1/chess-best-move'
    output.mkdir(parents=True,mode=0o700)
    admission=output/'ORPHAN_DEADLINE_ADMISSION.json'
    assert not admission.exists(), 'Do not start a duplicate orphan watcher'
    assert subprocess.check_output(['docker','info','--format','{{.ID}}'],text=True).strip()=='c6e16cdf-e878-4cc5-84c8-78a56c54b5c5'
    start=inspect_cli()
    assert start['alive_same_original_cli']
    save(admission,dict(at=time.time(),container=CID,remote_docker_identity=IDENTITY,
        original_cli_pid=PID,original_cli_start_ticks=TICKS,recovery_deadline=DEADLINE,
        original_override_seconds=10800,original_phase_start_not_persisted=True,
        conservative_predecessor_probe_time=DEADLINE-10800,
        first_recorder_run_start=1793561975.7101612,
        exact_original_deadline_compliance_not_claimed=True,
        primary_trial_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED',
        no_new_model_attempts=True,no_original_result_or_config_edits=True,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    signals=[]
    while True:
        current=inspect_cli()
        save(output/'ORPHAN_DEADLINE_STATUS.json',dict(at=time.time(),deadline=DEADLINE,
            current=current,signals=signals,original_cli_only=True))
        if not current['alive_same_original_cli']:
            break
        if time.time()>=DEADLINE:
            for action,grace in [('interrupt',30),('terminate',15),('kill',1)]:
                current=inspect_cli()
                if not current['alive_same_original_cli']:
                    break
                inspect_cli(action);signals.append(dict(action=action,at=time.time()))
                time.sleep(grace)
            current=inspect_cli()
            if current['alive_same_original_cli']:
                raise RuntimeError('Original orphan CLI did not stop at recovery boundary')
            break
        time.sleep(min(40,max(0.1,DEADLINE-time.time())))
    raw=output/'raw-agent'
    assert not raw.exists()
    subprocess.run(['docker','cp',CID+':/logs/agent',str(raw)],check=True,timeout=900)
    files=[]
    for p in sorted(raw.rglob('*')):
        if not p.is_file():continue
        digest=hashlib.sha256()
        with p.open('rb')as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        files.append(dict(path=str(p.relative_to(raw)),bytes=p.stat().st_size,sha256=digest.hexdigest()))
    save(output/'ORIGINAL_ORPHAN_AGENT_CLOSED_AND_ARCHIVED.json',dict(at=time.time(),
        primary_trial_classification='UNKNOWN_CONTROLLER_OOM_INTERRUPTED',
        observed_completion=current.get('completion'),signals=signals,
        files=files,official_reward=None,qualifying_success_not_claimed=True,
        original_container_retained_for_native_verifier=True,new_model_attempts=0,
        exact_original_deadline_compliance_not_claimed=True))


if __name__=='__main__':main()
