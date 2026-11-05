"""Fence only new staging, finish every started native setup, then transfer admission."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
import time

import collection_readiness_r7 as n


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())


def main():
    R=n.R;S=R/'stream/collection-r4';destination=R/'checks/controller-r7-admission-fence-r8.json'
    lock=(R/'checks/dispatch-handoff17-r8.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if destination.exists() or (R/'checks/CURRENT_DISPATCH_AUTHORITY_R8.json').exists():raise FileExistsError('Observe existing R8 authority or completed admission fence')
    replacement=R/'scripts/run_collection_stream_r8.py'
    for name in ['controller-r8-offline-acceptance-r3.json','controller-r8-reader-lifetime-acceptance-r3.json']:
        proof=read(R/'checks'/name)
        if not proof['passed'] or proof['controller_source_sha256']!=n.sha(replacement):raise ValueError('New controller acceptance changed')
    if not read(R/'checks/derived-reader-activation-r8.json')['collection_admission_budget_changed'] is False:raise ValueError('Derived reader activation altered admission budget')
    if (R/'scripts/export_native_canary_calls.py').resolve()!=R/'scripts/export_native_canary_calls_r8.py' or (R/'scripts/audit_collection_results.py').resolve()!=R/'scripts/audit_collection_results_r8.py':raise ValueError('Legacy data readers are not retired')
    for old in [35765,1182007]:
        if Path('/proc/'+str(old)).exists():raise ValueError('Old strict-count finite preparer still alive')
    authority=read(R/'checks/CURRENT_DISPATCH_AUTHORITY_R7.json');root=Path(authority['state_path']).parent
    manifest=read(Path(authority['manifest']));pid=authority['pid'];proc=Path('/proc')/str(pid)
    if n.sha(Path(authority['manifest']))!=authority['manifest_sha256']:raise ValueError('Old Campaign changed')
    if any(n.sha(R/'scripts'/name)!=digest for name,digest in manifest['helper_sha256'].items()):raise ValueError('Old frozen source changed')
    if str(R/'scripts/run_collection_stream_r7.py').encode() not in (proc/'cmdline').read_bytes().split(b'\0'):raise ValueError('Old controller PID identity changed')
    ticks=(proc/'stat').read_text().rsplit(')',1)[1].split()[19]
    oldenv=dict(x.split(b'=',1) for x in (proc/'environ').read_bytes().split(b'\0') if b'=' in x)
    if not oldenv.get(b'DEEPSEEK_API_KEY'):raise ValueError('Authorized existing model service environment absent')
    env={k.decode():v.decode() for k,v in oldenv.items()}
    progress=R/'checks/controller-r8-native-handoff-progress.json';started=time.monotonic()
    def save(stage,**extra):
        value=dict(stage=stage,checked_at=now(),pid=os.getpid(),old_controller_pid=pid,teacher_or_verifier_signals=0,**extra)
        tmp=progress.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(progress)
    def same():
        if not proc.exists() or (proc/'stat').read_text().rsplit(')',1)[1].split()[19]!=ticks:raise ValueError('Old controller exited before the native admission fence completed')
    def check_time():
        if time.monotonic()-started>21600:raise TimeoutError('Existing native Trials remain untouched; inspect actual pending names')
    # Complete the newly moved build chain before this second wiring change.
    while True:
        accepted=[]
        for file in (R/'stream/direct17-native-source-r17/environment-outcomes').glob('*.json'):
            item=read(file)
            if item['status']!='ENV_READY':continue
            build=Path(item['original_context_build']);receipt=read(build)
            if receipt.get('builder_engine_id')!=n.NODE['engine_id']:continue
            if n.sha(build)!=item['original_context_build_sha256']:raise ValueError('Original private17 build receipt changed')
            for kind in ['install','nop']:
                result=Path(item['native_'+kind+'_trial'])/'result.json'
                if n.sha(result)!=item[kind+'_result_sha256']:raise ValueError('New private-engine native check Result changed')
                native=read(result)
                if native['exception_info'] or native['infrastructure_errors']:raise ValueError('Private build-chain native acceptance has infrastructure failure')
            accepted.append(dict(task_id=item['task_id'],receipt=str(file),receipt_sha256=n.sha(file),build=str(build),build_sha256=n.sha(build)))
        if accepted:break
        same();check_time();save('WAITING_FOR_FIRST_ORIGINAL_CONTEXT_PRIVATE_ENGINE17_NATIVE_READY',active_teacher_trials=read(root/'state.json')['actual_teacher_trials']);time.sleep(2)
    staging=S/'staging-dispatches';mode=stat.S_IMODE(staging.stat().st_mode);drained=False;fenced=False
    try:
        if not mode&stat.S_IWUSR:raise ValueError('Unexpected prior staging admission fence')
        os.chmod(staging,mode&~0o222);fenced=True
        gate=R/'checks/controller-r7-staging-admission-fence-r8.json'
        n.freeze(gate,dict(checked_at=now(),old_pid=pid,old_process_start_ticks=ticks,directory=str(staging),original_mode=mode,fenced_mode=stat.S_IMODE(staging.stat().st_mode),
            old_source_sha256=n.sha(R/'scripts/run_collection_stream_r7.py'),reason='Allow every already-created native setup and teacher to finish; deny only creation of a new pre-queue staging directory',teacher_or_verifier_signals=0,model_calls=0))
        while True:
            same();check_time()
            events=[json.loads(line) for line in (S/'teacher-lifecycle.jsonl').read_text().splitlines()]
            admitted={x['trial_name']:x for x in events if x['event']=='TEACHER_ADMITTED'}
            pending=[]
            for file in staging.glob('*/setup.json'):
                item=read(file)
                if not (S/'trials'/item['trial_name']/'result.json').exists() and item['trial_name'] not in admitted:pending.append(item)
            state=read(root/'state.json')
            save('WAITING_ONLY_FOR_ALREADY_STARTED_NATIVE_SETUPS_TO_ADMIT_OR_FINISH',pending_native_setups=pending,
                actual_teacher_trials=state['actual_teacher_trials'],native_staging_directory_fenced=True,
                pre_queue_permission_rejections_are_not_model_attempts=True,first_private_build_chain_acceptances=accepted)
            if not pending:break
            time.sleep(2)
        drain=root/'DRAIN_REQUESTED.json'
        n.freeze(drain,dict(requested_at=now(),old_pid=pid,old_process_start_ticks=ticks,replacement_source_sha256=n.sha(replacement),
            reason='Use proved actual/conservative attempt counts after legacy readers retire; keep both pool buffers supplied. Every native setup has already admitted or finished.',staging_gate=str(gate),staging_gate_sha256=n.sha(gate)))
        observations=[]
        while len(observations)<2:
            state=read(root/'state.json')
            if not proc.exists():
                terminal=root/'DRAINED.json'
                if not terminal.exists():raise ValueError('Old controller exited without native drain evidence')
                observations.append(dict(observed_at=now(),state_checked_at=state['checked_at'],actual_teacher_trials=0,native_drained_sha256=n.sha(terminal)))
            else:
                same()
                if state['status']=='DRAINING_NATIVE_TEACHERS' and (not observations or observations[-1]['state_checked_at']!=state['checked_at']):
                    observations.append(dict(observed_at=now(),state_checked_at=state['checked_at'],actual_teacher_trials=state['actual_teacher_trials']))
            time.sleep(1)
        drained=True
        active={};all_admitted={}
        for line in (S/'teacher-lifecycle.jsonl').open():
            value=json.loads(line)
            if value['event']=='TEACHER_ADMITTED':
                item=dict(task_id=value['task_id'],pool=value['pool'],agent_admitted_at=value['agent_admitted_at'],controller_revision=value.get('controller_revision'))
                active[value['trial_name']]=item;all_admitted[value['trial_name']]=item
            elif value['event']=='TEACHER_FINALIZED':active.pop(value['trial_name'],None)
        if len(active)>8:raise ValueError('Actual teacher cap exceeded before transfer')
        inherited=set(active);native={}
        for file in staging.glob('*/setup.json'):
            item=read(file)
            if not (S/'trials'/item['trial_name']/'result.json').exists():native[item['trial_name']]=item['task_id']
        for file in (S/'dispatches').glob('*/dispatch.json'):
            item=read(file)
            if item['kind']=='teacher' and not (S/'trials'/item['trial_name']/'result.json').exists():
                if item['trial_name'] not in all_admitted:raise ValueError('Teacher dispatch has no actual native admission evidence')
                inherited.add(item['trial_name'])
        blocks={}
        positives={}
        for file in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            item=read(file)
            if item['status']=='ENV_READY':positives.setdefault(item['task_id'],[]).append(file)
        for file in (root/'setup-failures').glob('*.json'):
            item=read(file);ident=item['task_id'];result=Path(item['native_result'])
            failure_time=datetime.datetime.fromisoformat(read(result)['finished_at'].replace('Z','+00:00'))
            if any(value['task_id']==ident and datetime.datetime.fromisoformat(value['agent_admitted_at'])>failure_time for value in all_admitted.values()):continue
            files=positives.get(ident,[])
            if any(datetime.datetime.fromisoformat(read(Path(read(p)['native_nop_trial'])/'result.json')['finished_at'].replace('Z','+00:00'))>failure_time for p in files):continue
            if files:blocks[ident]=dict(result=str(result),result_sha256=n.sha(result),blocked_ready_receipt_sha256s=sorted(n.sha(p) for p in files))
        fence=dict(checked_at=now(),old_pid=pid,old_process_start_ticks=ticks,old_native_admission_disabled=True,
            drain_request=str(drain),drain_request_sha256=n.sha(drain),drain_observations=observations,previous_revision_root=str(root),
            inherited_teacher_trial_names=sorted(inherited),inherited_active_metadata={name:all_admitted[name] for name in inherited},
            inherited_native_trial_names=sorted(native),native_trial_task_ids=native,inherited_preparing_task_ids=state['preparing_environments'],
            setup_readiness_blocks=blocks,staging_gate=str(gate),staging_gate_sha256=n.sha(gate),
            first_private_build_chain_acceptances=accepted,new_dispatch_authority_node='149',new_runtime_node='17',teacher_global_cap=8,
            old_processes_killed=0,old_trials_cancelled_or_replayed=0,model_service_environment='Copied from old authorized controller in memory; no values recorded',
            source_sha256=n.sha(Path(__file__)))
        n.freeze(destination,fence)
        os.chmod(staging,mode);fenced=False
        save('OLD_NEW_ADMISSION_DISABLED_EXEC_ACCEPTED_R8',inherited_actual_teachers=len(active),old_healthy_trials_preserved=True)
        print(json.dumps(dict(status='OLD_NEW_ADMISSION_DISABLED_EXEC_ACCEPTED_R8',inherited_actual_teachers=len(active),pid=os.getpid())),flush=True)
        interpreter='/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
        os.execve(interpreter,[interpreter,str(replacement)],env)
    finally:
        if fenced and not drained:os.chmod(staging,mode)


if __name__=='__main__':main()
