"""Fence only the old zero-model dispatch directory after both current NOPs start.

Current native Trial/Result/log directories remain writable. No signal, source
edit, Task edit, container cancellation or model dispatch occurs here.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

R=Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S=R/'stream/tmax-resident-buffer-preflight-r1'
PID=114260


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def current_nops():
    state=json.loads((S/'state.json').read_text());active=set(state.get('active_task_ids',[]))
    if len(active)!=2:return None
    found={}
    for p in (S/'dispatches').glob('*/dispatch.json'):
        v=json.loads(p.read_text())
        if v['task_id'] not in active or v['kind']!='nop':continue
        trial=S/'trials'/v['trial_name']
        if (trial/'result.json').exists():continue
        config=json.loads((p.parent/'trial-config.json').read_text())
        if config['agent']['name']!='nop':raise ValueError('Legacy acceptance unexpectedly contains a model agent')
        compose=list(trial.glob('remote-docker-*.compose.json'))
        if len(compose)!=1:continue
        identity=compose[0].name.removeprefix('remote-docker-').removesuffix('.compose.json')
        reply=subprocess.run(['docker','ps','--filter','label=io.harbor.remote-docker.identity='+identity,'--format','{{.ID}}'],capture_output=True,text=True,check=True,timeout=15)
        if len(reply.stdout.split())!=1:continue
        found[v['task_id']]=dict(task_id=v['task_id'],trial_name=v['trial_name'],trial=str(trial),
            native_config=str(p.parent/'trial-config.json'),native_config_sha256=sha(p.parent/'trial-config.json'),
            running_container=reply.stdout.strip(),identity=identity)
    return found if set(found)==active else None


def main():
    lock=(R/'checks/legacy-resident-preparation-retirement-r7.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    proof=R/'checks/legacy-resident-preparation-admission-fence-r7.json'
    if proof.exists():raise FileExistsError('Observe existing retirement fence; never duplicate it')
    proc=Path('/proc')/str(PID)
    if str(R/'scripts/prepare_resident_tmax_buffer149_r1.py').encode() not in (proc/'cmdline').read_bytes().split(b'\0'):
        raise ValueError('Legacy PID identity changed')
    plan=json.loads((S/'PLAN.json').read_text())
    if sha(R/'scripts/prepare_resident_tmax_buffer149_r1.py')!=plan['source_sha256']:raise ValueError('Frozen legacy source changed')
    directory=S/'dispatches';original_mode=stat.S_IMODE(directory.stat().st_mode)
    while True:
        running=current_nops()
        if running is None:time.sleep(1);continue
        before={p.name for p in directory.iterdir()}
        os.chmod(directory,original_mode & ~0o222)
        second=current_nops()
        after={p.name for p in directory.iterdir()}
        if second is None or set(second)!=set(running) or after!=before:
            os.chmod(directory,original_mode);time.sleep(1);continue
        existing={p.stem for p in (S/'environment-outcomes').glob('*.json')}
        retired=[x['task_id'] for x in plan['tasks'] if x['task_id'] not in existing and x['task_id'] not in running]
        value=dict(checked_at=now(),status='LEGACY_ZERO_MODEL_ADMISSION_FENCED_CURRENT_NATIVE_NOPS_PRESERVED',
            old_pid=PID,old_process_start_ticks=(proc/'stat').read_text().split()[21],
            source_sha256=plan['source_sha256'],source_plan_sha256=sha(S/'PLAN.json'),
            directory=str(directory),original_mode=oct(original_mode),fenced_mode=oct(stat.S_IMODE(directory.stat().st_mode)),
            currently_running_nops=list(running.values()),retired_unstarted_task_ids=retired,
            existing_native_trial_directories_unmodified=True,task_files_or_resources_modified=False,
            current_trials_cancelled_or_replayed=0,teacher_or_verifier_signals=0,model_calls=0,
            classification='Permission errors for these retired unstarted IDs under this exact management directory are ADMINISTRATIVE_PREPARATION_RETIREMENT, not genuine Task environment failures;17 continues their preparation')
        with proof.open('x') as stream:json.dump(value,stream,indent=2)
        break
    while proc.exists():time.sleep(2)
    results=[]
    for x in running.values():
        file=Path(x['trial'])/'result.json'
        if not file.exists():raise ValueError('Current native NOP did not retain its terminal Result')
        v=json.loads(file.read_text())
        results.append(dict(trial=x['trial_name'],result=str(file),result_sha256=sha(file),
            finished_at=v.get('finished_at'),exception=v.get('exception_info'),infrastructure_errors=v.get('infrastructure_errors'),
            verifier_completed=bool((v.get('verifier') or {}).get('finished_at')),rewards=(v.get('verifier_result') or {}).get('rewards')))
    out=dict(status='LEGACY_PREPARER_EXITED_WITH_NATIVE_CURRENT_TRIAL_RESULTS_RETAINED',checked_at=now(),
        fence=str(proof),fence_sha256=sha(proof),current_nop_results=results,old_pid=PID,
        model_calls=0,current_trial_signals=0,retired_unstarted_tasks=len(retired))
    with (R/'checks/legacy-resident-preparation-retired-r7.json').open('x') as stream:json.dump(out,stream,indent=2)
    print(json.dumps(out),flush=True)


if __name__=='__main__':main()
