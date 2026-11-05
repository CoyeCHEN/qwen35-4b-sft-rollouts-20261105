"""Fence R5 new admissions, retain its native lifecycles, exec the sole writer.

The writer stays on149. Existing R5 Trial END events retain global permits inR6;
this is explicit admission ownership transfer, not a cross-host flock claim.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import time
import collection_readiness_r6 as n
import run_collection_stream_r4 as c


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    lock = (n.R / 'checks/dispatch-handoff17-r6.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    scope = n.R / 'stream/collection-r4'
    if (n.D / 'CAMPAIGN.json').exists() or (n.R / 'checks/CURRENT_DISPATCH_AUTHORITY_R6.json').exists():
        raise FileExistsError('New dispatch authority already exists; observe it')
    # Reuse two completed, hash-verified native17 environment acceptances.
    # No model Trial is replayed and no old proof is rewritten.
    for rev in ['r3', 'r4']:
        file = n.R / ('checks/private17-native-task-acceptance-' + rev + '.json')
        accepted = json.loads(file.read_text())
        ident = accepted['task_id']
        if c.attempt_counts()[ident]:
            continue
        if accepted['status'] != 'ENV_READY' or accepted['engine_id'] != n.NODE['engine_id'] or not accepted['environment_and_storage_accepted']:
            raise ValueError('Prior private17 native environment acceptance differs')
        row = next(r for r in c.frozen_rows() if r['task_id'] == ident)
        admitted = n.prepare_identity(row)
        for key in ['image_id', 'instruction_sha256', 'prepared_task_toml_sha256', 'verifier_files']:
            if admitted[key] != accepted['admitted_task'][key]:
                raise ValueError('Prior accepted Task identity changed: ' + key)
        out = dict(task_id=ident, pool=row['pool'], status='ENV_READY', admitted_task=admitted,
            native_install_trial=accepted['install_trial'], native_nop_trial=accepted['nop_trial'],
            install_result_sha256=accepted['install_result_sha256'], nop_result_sha256=accepted['nop_result_sha256'],
            nop_reward=accepted['nop_reward'], engine_id=n.NODE['engine_id'], deployment_config_sha256=n.CONFIG_SHA,
            placement=admitted['deployment_assignment'], placement_sha256=admitted['deployment_assignment_sha256'],
            prior_native17_acceptance=str(file), prior_native17_acceptance_sha256=n.sha(file),
            deployment_revision_difference='Project namespace and explicit config binding; same Engine, original image/resources/test/wheel/teacher and dependency index',
            teacher_success_not_implied=True, model_calls=0)
        for kind in ['install', 'nop']:
            if n.sha(Path(out['native_' + kind + '_trial']) / 'result.json') != out[kind + '_result_sha256']:
                raise ValueError('Original native acceptance Result changed')
        n.freeze(n.D / 'environment-outcomes' / (ident + '.json'), out)
    while not list((n.D / 'environment-outcomes').glob('*.json')):
        time.sleep(5)
    old = json.loads((n.R / 'campaign-state.json').read_text())
    pid = old['pid']
    proc = Path('/proc') / str(pid)
    argv = (proc / 'cmdline').read_bytes().split(b'\0')
    if str(n.R / 'scripts/run_collection_stream_r5.py').encode() not in argv:
        raise ValueError('Old PID is not the declared native R5 controller')
    source = json.loads((scope / 'CAMPAIGN.json').read_text())
    if any(n.sha(n.R / 'scripts' / name) != digest for name, digest in source['helper_sha256'].items()):
        raise ValueError('Old frozen source changed; handoff requires investigation')
    env = dict(os.environ)
    original_env = dict(item.split(b'=', 1) for item in (proc / 'environ').read_bytes().split(b'\0') if b'=' in item)
    if not original_env.get(b'DEEPSEEK_API_KEY'):
        raise ValueError('Authorized service environment absent')
    env['DEEPSEEK_API_KEY'] = original_env[b'DEEPSEEK_API_KEY'].decode()
    started = (proc / 'stat').read_text().split()[21]
    drain = scope / 'DRAIN_REQUESTED.json'
    n.freeze(drain, dict(requested_at=now(),reason='User-authorized17 SSD deployment handoff; stop new R5 admissions and retain all healthy native lifecycles',
        old_pid=pid,old_process_start_ticks=started,replacement_source_sha256=n.sha(n.R / 'scripts/run_collection_stream_r6.py')))
    observations = []
    while len(observations) < 2:
        state = json.loads((n.R / 'campaign-state.json').read_text())
        if state.get('pid') != pid or state.get('status') != 'DRAINING_NATIVE_TEACHERS':
            time.sleep(1)
            continue
        observations.append(dict(checked_at=now(),state_checked_at=state['checked_at'],actual_teacher_trials=state['actual_teacher_trials'],status=state['status']))
        time.sleep(2)
    active = {}
    for line in (scope / 'teacher-lifecycle.jsonl').open():
        value = json.loads(line)
        if value['event'] == 'TEACHER_ADMITTED':
            active[value['trial_name']] = {k:value[k] for k in ['task_id','pool','agent_admitted_at']}
        elif value['event'] == 'TEACHER_FINALIZED':
            active.pop(value['trial_name'], None)
    if len(active) > 8:
        raise ValueError('Actual old teacher concurrency exceeds the authorized cap')
    native = {}
    for file in (scope / 'staging-dispatches').glob('*/setup.json'):
        value = json.loads(file.read_text())
        if not (scope / 'trials' / value['trial_name'] / 'result.json').exists():
            native[value['trial_name']] = value['task_id']
    fence = dict(checked_at=now(),old_pid=pid,old_process_start_ticks=started,
        old_controller_source_sha256=n.sha(n.R / 'scripts/run_collection_stream_r5.py'),
        old_native_admission_disabled=True,drain_request=str(drain),drain_request_sha256=n.sha(drain),
        actual_drain_observations=observations,inherited_teacher_trial_names=sorted(active),inherited_active_metadata=active,
        inherited_native_trial_names=sorted(native),native_trial_task_ids=native,
        teacher_global_cap=8,new_dispatch_authority_node='149',new_runtime_node='17',
        native_permit_release='Original R5 END after verifier, native artifact collection and cleanup; no PID kill or Trial replay',
        previous_controller_role='NATIVE_LIFECYCLE_FINALIZATION_ONLY_NO_NEW_DISPATCH_AUTHORITY')
    n.freeze(n.R / 'checks/controller-r5-admission-fence-r6.json', fence)
    print(json.dumps(dict(status='OLD_NATIVE_ADMISSION_FENCED_EXECUTING_R6',old_pid=pid,inherited_teachers=len(active),new_pid=os.getpid())),flush=True)
    interpreter = '/home/chenkeyi/.local/share/harbor-rsi/qwen35-m1-m2-tb21-20261026/venv/bin/python'
    os.execve(interpreter, [interpreter,str(n.R / 'scripts/run_collection_stream_r6.py')],env)


if __name__ == '__main__':
    main()
