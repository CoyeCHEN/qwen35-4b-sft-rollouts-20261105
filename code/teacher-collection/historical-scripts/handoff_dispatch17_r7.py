"""Transfer only new admission; retain every healthy old native lifecycle."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import time
import collection_readiness_r7 as n
import run_collection_stream_r4 as c
from collection_selection_r7 import active_rows


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    lock=(n.R/'checks/dispatch-handoff17-r7.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (n.D/'CAMPAIGN.json').exists() or (n.R/'checks/CURRENT_DISPATCH_AUTHORITY_R7.json').exists():
        raise FileExistsError('Observe existing R7 authority; never duplicate it')
    accepted=n.R/'checks/deployment17-r7b-offline-and-resource-acceptance.json'
    assert json.loads(accepted.read_text())['status']=='R7_SELECTION_PARITY_ASYNC_HEARTBEAT_PYTHONLESS_CF_RESOURCE_AND_NATIVE_CONFIGS_ACCEPTED'
    previous=json.loads((n.R/'checks/CURRENT_DISPATCH_AUTHORITY_R6.json').read_text())
    root=Path(previous['state_path']).parent
    pid=previous['pid'];proc=Path('/proc')/str(pid)
    assert str(n.R/'scripts/run_collection_stream_r6.py').encode() in (proc/'cmdline').read_bytes().split(b'\0')
    manifest=json.loads((root/'CAMPAIGN.json').read_text())
    assert all(n.sha(n.R/'scripts'/name)==value for name,value in manifest['helper_sha256'].items())
    rows={r['task_id']:r for r in active_rows(c.attempt_counts())}
    positives={}
    for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
        value=json.loads(path.read_text())
        if value['status']=='ENV_READY':positives[value['task_id']]=(path,value)
    adopted=[]
    for ident,(file,value) in positives.items():
        if n.blocking_review(ident):continue
        admitted=n.prepare_identity(rows[ident])
        for key in ['image_id','instruction_sha256','prepared_task_toml_sha256','verifier_files']:
            if admitted[key]!=value['admitted_task'][key]:raise ValueError('Source identity differs at17 handoff: '+ident+':'+key)
        for kind in ['install','nop']:
            if n.sha(Path(value['native_'+kind+'_trial'])/'result.json')!=value[kind+'_result_sha256']:
                raise ValueError('Prior original native Result changed')
        out=dict(value,admitted_task=admitted,deployment_config_sha256=n.CONFIG_SHA,
            placement=admitted['deployment_assignment'],placement_sha256=admitted['deployment_assignment_sha256'],
            prior_native17_acceptance=str(file),prior_native17_acceptance_sha256=n.sha(file),
            deployment_revision_difference='Same Engine/image/resources/tests/wheel/teacher/dependency mirror; R7 changes bounded preparation and planning/probe implementation')
        n.freeze(n.D/'environment-outcomes'/(ident+'.json'),out);adopted.append(ident)
    oldenv=dict(x.split(b'=',1) for x in (proc/'environ').read_bytes().split(b'\0') if b'=' in x)
    assert oldenv.get(b'DEEPSEEK_API_KEY')
    env=dict(os.environ);env['DEEPSEEK_API_KEY']=oldenv[b'DEEPSEEK_API_KEY'].decode()
    start=(proc/'stat').read_text().split()[21]
    drain=root/'DRAIN_REQUESTED.json'
    n.freeze(drain,dict(requested_at=now(),reason='Bounded8 preparation and nonblocking planning; preserve all active native teachers',old_pid=pid,old_process_start_ticks=start,replacement_source_sha256=n.sha(n.R/'scripts/run_collection_stream_r7.py')))
    observations=[]
    while len(observations)<2:
        state=json.loads((root/'state.json').read_text())
        if state['pid']==pid and state['status']=='DRAINING_NATIVE_TEACHERS':
            observations.append(dict(observed_at=now(),state_checked_at=state['checked_at'],actual_teacher_trials=state['actual_teacher_trials']))
        time.sleep(2)
    scope=n.R/'stream/collection-r4';active={}
    for line in (scope/'teacher-lifecycle.jsonl').open():
        value=json.loads(line)
        if value['event']=='TEACHER_ADMITTED':
            active[value['trial_name']]=dict(task_id=value['task_id'],pool=value['pool'],agent_admitted_at=value['agent_admitted_at'],controller_revision=value.get('controller_revision','r5'))
        elif value['event']=='TEACHER_FINALIZED':active.pop(value['trial_name'],None)
    assert len(active)<=8
    native={}
    for file in (scope/'staging-dispatches').glob('*/setup.json'):
        value=json.loads(file.read_text())
        if not (scope/'trials'/value['trial_name']/'result.json').exists():native[value['trial_name']]=value['task_id']
    fence=dict(checked_at=now(),old_pid=pid,old_process_start_ticks=start,old_native_admission_disabled=True,
        drain_request=str(drain),drain_request_sha256=n.sha(drain),drain_observations=observations,
        previous_revision_root=str(root),inherited_preparing_task_ids=state['preparing_environments'],
        inherited_teacher_trial_names=sorted(active),inherited_active_metadata=active,
        inherited_native_trial_names=sorted(native),native_trial_task_ids=native,
        predecessor_r5_fence=str(n.R/'checks/controller-r5-admission-fence-r6.json'),
        predecessor_r5_fence_sha256=n.sha(n.R/'checks/controller-r5-admission-fence-r6.json'),
        adopted_native17_readiness=adopted,new_dispatch_authority_node='149',new_runtime_node='17',teacher_global_cap=8,
        old_processes_killed=0,old_trials_cancelled_or_replayed=0)
    n.freeze(n.R/'checks/controller-r6-admission-fence-r7.json',fence)
    print(json.dumps(dict(status='NATIVE_PREDECESSORS_FENCED_EXEC_R7',pid=os.getpid(),inherited_teachers=len(active),adopted_ready=len(adopted))),flush=True)
    interpreter='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
    os.execve(interpreter,[interpreter,str(n.R/'scripts/run_collection_stream_r7.py')],env)


if __name__=='__main__':main()
