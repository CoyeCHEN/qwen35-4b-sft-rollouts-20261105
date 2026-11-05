"""Resume the fully drained native campaign once the original service is available."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from uuid import uuid4

import collection_readiness_r22 as n
import run_collection_stream_r22 as controller
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
from collection_current_setup_blocks_r453 import current_setup_blocks
from collection_administrative_ready_r427 import reconcile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    R, S = n.R, n.R/'stream/collection-r4'
    lock = (R/'checks/dispatch-handoff17-r22.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fence_path = R/'checks/controller-r21-admission-fence-r22.json'
    if fence_path.exists() or (R/'checks/CURRENT_DISPATCH_AUTHORITY_R22.json').exists() or (Path(n.DEPLOYMENT['controller_root'])/'CAMPAIGN.json').exists():
        raise FileExistsError('Observe existing R22 authority or partial handoff; never replay')
    if Path('/etc/machine-id').read_text().strip() != n.DEPLOYMENT['controller_machine_id']:
        raise ValueError('Only the declared149 control host may grant dispatch; this is not a distributed flock')
    accepted_path = R/'checks/controller-r22-offline-acceptance-r443.json'
    accepted = controller.read(accepted_path)
    assert accepted['passed'] and accepted['controller_source_sha256'] == n.sha(R/'scripts/run_collection_stream_r22.py')
    assert accepted['deployment_config_sha256'] == n.CONFIG_SHA
    assert all(n.sha(R/'scripts'/name) == digest for name,digest in accepted['helper_sha256'].items())
    assert controller.validate_controller_runtime() == accepted['controller_runtime']
    known = R/'checks/KNOWN_VERIFIER_READY_ACCEPTANCE_R456.json'
    assert controller.read(known)['passed'] and controller.read(known)['helper_source_sha256'] == n.sha(R/'scripts/collection_current_setup_blocks_r453.py')
    old_authority_path = R/'checks/CURRENT_DISPATCH_AUTHORITY_R21.json'
    authority = controller.read(old_authority_path)
    previous = Path(authority['manifest'])
    assert n.sha(previous) == authority['manifest_sha256']
    assert all(n.sha(R/'scripts'/name) == digest for name,digest in controller.read(previous)['helper_sha256'].items())
    old_root = Path(authority['state_path']).parent
    assert not Path('/proc/'+str(authority['pid'])).exists()
    assert controller.read(old_root/'DRAINED.json')['status'] == 'DRAINED_WITH_NO_ACTIVE_TEACHERS'
    assert controller.read(old_root/'DRAIN_REQUESTED.json')['reason'] == 'AUTHORIZED_TEACHER_SERVICE_HTTP402_INSUFFICIENT_BALANCE'
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = (process/'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        assert not any(value.startswith(str(R/'scripts/run_collection_stream_r').encode()) for value in argv), 'An existing native collection writer must be observed, not duplicated'
    active = {}
    for line in (S/'teacher-lifecycle.jsonl').open():
        event = json.loads(line)
        if event['event'] == 'TEACHER_ADMITTED':
            active[event['trial_name']] = event
        elif event['event'] in ['TEACHER_AGENT_ENDED','TEACHER_FINALIZED']:
            active.pop(event['trial_name'],None)
    assert not active
    for path in (S/'staging-dispatches').glob('*/setup.json'):
        assert (S/'trials'/controller.read(path)['trial_name']/'result.json').exists(), 'Preserve unfinished original native setup'
    for path in R.glob('stream/*/dispatches/*/dispatch.json'):
        item = controller.read(path)
        if item['kind'] == 'teacher':
            assert (path.parents[2]/'trials'/item['trial_name']/'result.json').exists(), 'An original teacher is unfinished'
    counts = attempt_counts()
    rows = active_rows(counts)
    qualified = {json.loads(line)['task_id'] for pool in ['CALIBFORGE','TMAX'] for line in (R/'indexes'/(pool+'_SUCCESS_INDEX.jsonl')).open()}
    eligible_ids = {row['task_id'] for row in rows if row['task_id'] not in qualified and counts[row['task_id']] < 2}
    assert eligible_ids, 'Collection has no remaining authorized Task; finalize the data instead'
    positives, files = {}, {}
    for root in n.readiness_roots():
        for path in [*sorted((root/'environment-outcomes').glob('*.json')),*sorted((root/'ready-revisions').glob('*/*.json'))]:
            value = controller.read(path)
            if value['task_id'] in eligible_ids and value['status'] == 'ENV_READY':
                positives[value['task_id']] = n.normalize_ready(value,path)
                files.setdefault(value['task_id'],[]).append(path)
    blocks, administrative = reconcile(R,positives,current_setup_blocks(R,positives))
    current_blocks = {ident:value for ident,value in blocks.items() if ident in eligible_ids}
    usable = sorted(set(positives)-set(current_blocks))
    assert usable, 'No accepted Task is ready; keep independent preparation active'
    # Keep credentials only in process memory; never use a secret argv or file.
    raw_environment = subprocess.run(['tmux','-L','cf-tmax-teacher-20261029','show-environment','-g'],capture_output=True,text=True,check=True).stdout
    key = next((line.split('=',1)[1] for line in raw_environment.splitlines() if line.startswith('DEEPSEEK_API_KEY=')),None)
    raw_environment = None
    assert key, 'Original authorized tmux service environment absent'
    request = urllib.request.Request('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+key},method='GET')
    observation = dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),endpoint=request.full_url,
        provider_changed=False,unknown_proxy_used=False,model_calls=0,task_attempts=0,credential_or_balance_amounts_written=False)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=30) as response:
            data = json.loads(response.read())
            assert isinstance(data.get('is_available'),bool)
            observation.update(http_status=response.status,balance_available=data['is_available'])
    except urllib.error.HTTPError as error:
        observation.update(http_status=error.code,balance_available=None,error_type='HTTPError')
    except (OSError,ValueError) as error:
        observation.update(balance_available=None,error_type=type(error).__name__)
    observation_path = R/'checks/service-restoration-r22'/(uuid4().hex+'.json')
    controller.freeze(observation_path,observation)
    preview = dict(checked_at=controller.now(),status='PRELAUNCH_SERVICE_AVAILABLE' if observation.get('balance_available') is True else 'PRELAUNCH_BLOCKED_ORIGINAL_SERVICE_BALANCE',
        old_native_controller_fully_exited=True,old_native_drained_sha256=n.sha(old_root/'DRAINED.json'),
        existing_teacher_trials_preserved=True,actual_or_conservative_attempts=sum(counts.values()),
        attempted_independent_tasks=len(counts),remaining_authorized_tasks=sorted(eligible_ids),
        validated_ready_tasks=usable,environment_blocks=current_blocks,administrative_reconciliations=administrative,
        service_observation=str(observation_path),service_observation_sha256=n.sha(observation_path),
        controller_source_sha256=n.sha(R/'scripts/run_collection_stream_r22.py'),deployment_config_sha256=n.CONFIG_SHA,
        check_only=args.check_only,new_controller_started=False,teacher_dispatches=0,model_calls=0,
        source_sha256=n.sha(Path(__file__)))
    preview_path = R/'checks/controller-r22-prelaunch-r444'/(uuid4().hex+'.json')
    controller.freeze(preview_path,preview)
    if args.check_only or observation.get('balance_available') is not True:
        key = request = None
        print(json.dumps(dict(preview=str(preview_path),status=preview['status'],ready=len(usable),unfinished=len(eligible_ids),new_controller_started=False,model_calls=0)))
        return
    assert attempt_counts() == counts
    fence = dict(checked_at=controller.now(),old_pid=authority['pid'],old_controller_fully_exited=True,old_native_admission_disabled=True,
        drain_request=str(old_root/'DRAIN_REQUESTED.json'),drain_request_sha256=n.sha(old_root/'DRAIN_REQUESTED.json'),
        native_drained=str(old_root/'DRAINED.json'),native_drained_sha256=n.sha(old_root/'DRAINED.json'),previous_revision_root=str(old_root),
        inherited_teacher_trial_names=[],inherited_active_metadata={},inherited_native_trial_names=[],native_trial_task_ids={},inherited_preparing_task_ids=[],
        setup_readiness_blocks={ident:dict(result=value['native_result'],result_sha256=value['native_result_sha256'],blocked_ready_receipt_sha256s=sorted(n.sha(path) for path in files.get(ident,[]))) for ident,value in current_blocks.items()},
        service_recovery_evidence=str(observation_path),service_recovery_evidence_sha256=n.sha(observation_path),
        new_dispatch_authority_node='149',new_runtime_node='17',teacher_global_cap=8,
        cross_node_authority='Only149 may own admission;17 executes native environments. A node-local flock is not claimed as a distributed lock.',
        prelaunch_proof=str(preview_path),prelaunch_proof_sha256=n.sha(preview_path),
        old_authority_sha256=n.sha(old_authority_path),offline_acceptance_sha256=n.sha(accepted_path),
        known_existing_verifier_review_sha256=n.sha(known),current_setup_reader_sha256=n.sha(R/'scripts/collection_current_setup_blocks_r453.py'),
        old_processes_killed=0,old_trials_cancelled_or_replayed=0,attempt_counter_sha256=n.sha(R/'scripts/collection_attempts_r8.py'),
        model_service_environment='Original149 tmux authorized environment copied in memory; no key values recorded',source_sha256=n.sha(Path(__file__)))
    controller.freeze(fence_path,fence)
    env = dict(os.environ,DEEPSEEK_API_KEY=key)
    interpreter = n.DEPLOYMENT['controller_runtime']['interpreter']
    os.execve(interpreter,[interpreter,str(R/'scripts/run_collection_stream_r22.py')],env)


if __name__=='__main__':
    main()
