"""Finite frozen campaign admission using Harbor's native bounded TrialQueue.

Per-task install/NOP diagnostics precede teacher dispatch. Original environment
preparers continue independently. No scheduler/provider/agent lifecycle added.
"""
import asyncio
from collections import Counter
import copy
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tomllib
from uuid import uuid4

import toml
from harbor.models.job.config import RetryConfig
from harbor.models.task.config import TaskConfig as NativeTaskConfig
from harbor.models.trial.config import TrialConfig
from harbor.trial.queue import TrialQueue

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = R / 'stream/collection-r4'
TEACHER_SHA = 'bf9069d53ec81d6f53a1a93f35bd61a0a8eadb42deafb4fc1c6540bf10afba2c'
WHEEL_SHA = 'c686ba3f429d8257a060cf6b6a6e4c5aa7d740f33b2d59180d9a2717b55d0db8'

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)

def attempt_counts():
    counts = Counter()
    for path in (R / 'jobs').glob('*/config.json'):
        cfg = read(path)
        if cfg.get('install_only') or not any(a.get('name') == 'open-harness' for a in cfg.get('agents', [])):
            continue
        if cfg.get('n_attempts', 1) != 1 or cfg.get('retry', {}).get('max_retries', 0) != 0:
            raise ValueError('Unexpected legacy repetition')
        counts.update(Path(t['path']).name for t in cfg['tasks'])
    for path in R.glob('stream/*/dispatches/*/dispatch.json'):
        item = read(path)
        if item['kind'] == 'teacher':
            counts[item['task_id']] += 1
    if sum(counts.values()) > 2000 or len(counts) > 1000 or max(counts.values(), default=0) > 2:
        raise ValueError('Authorized attempt cap exceeded')
    return counts

from collection_selection_r4 import active_rows, original_rows, MANIFESTS
from collection_readiness_r4 import basic_receipt, prepared, ensure_resident, verify_nop, blocking_review, release_cold_cache
from native_image_archive149_r1 import ImageCapacityError


def frozen_rows():
    return active_rows(attempt_counts())

def native_config(row, kind):
    base = read(R / 'configs/canary-summary-cf.json')
    teacher_file=R/'configs/teacher-native-11tools-summary-r1.json'
    declared=base['agents'][0]['kwargs']
    if sha(teacher_file)!=TEACHER_SHA or declared['wheel_sha256']!=WHEEL_SHA or declared['config']!=read(teacher_file):
        raise ValueError('Native base configuration is outside the frozen teacher contract')
    agent = copy.deepcopy(base['agents'][0])
    agent['override_timeout_sec'] = row['agent_timeout_override_sec']
    if kind == 'nop':
        agent = {'name': 'nop'}
    env = copy.deepcopy(base['environment'])
    env['kwargs']['project_namespace'] = 'cftmaxstreamr420261030'
    all_ids = sorted(r['task_id'] for r in original_rows())
    subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.241.0.0')) + all_ids.index(row['slot_id']) * 16, 28)))
    override = R / 'configs/stream-task-networks-r4' / (row['slot_id'] + '.json')
    value = dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)]))))
    if override.exists():
        if read(override) != value:raise ValueError('Frozen per-task network override changed')
    else:
        override.parent.mkdir(parents=True,exist_ok=True)
        with override.open('x') as stream:stream.write(json.dumps(value,indent=2))
    env['extra_docker_compose'] = [str(override)]
    return TrialConfig(task={'path': row['prepared_task_path']}, trials_dir=S / 'trials',
        agent=agent, environment=env, verifier=base['verifier'], install_only=kind == 'install')

def audited_second_attempts():
    """Only terminal, explicitly classified failures; pending success audits wait."""
    eligible=set()
    qualified=set()
    for pool in ['CALIBFORGE','TMAX']:
        success=R/'indexes'/(pool+'_SUCCESS_INDEX.jsonl')
        if success.exists():qualified.update(json.loads(line)['task_id'] for line in success.open())
        failure=R/'indexes'/(pool+'_FAILURE_OR_PENDING_INDEX.jsonl')
        if not failure.exists():continue
        for line in failure.open():
            row=json.loads(line)
            classification=row['classification']
            if 'PENDING' in classification or 'REQUIRES_VERIFIER_LOG_CLASSIFICATION' in classification:continue
            eligible.add(row['task_id'])
    return eligible-qualified

def admission_candidates(rows, outcomes, pending, counts, second):
    """Ready teachers and fresh setup share each pool's fixed manifest order."""
    pools={pool:[] for pool in ['calibforge','tmax']}
    for row in rows:
        ident=row['task_id']
        if ident in pending:continue
        status=outcomes.get(ident,{}).get('status')
        if status=='ENV_READY':
            if counts[ident]==0 or (counts[ident]==1 and ident in second):
                pools[row['pool']].append((row,'teacher'))
        elif ident not in outcomes and basic_receipt(row) is not None:
            pools[row['pool']].append((row,'prepare'))
    return {pool:iter(items) for pool,items in pools.items()}

async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (R / 'campaign-stream-controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    gate = read(R / 'checks/CANARY_GATE.json')
    if not gate['passed'] or gate['unique_canary_tasks_by_pool'] != {'calibforge': 8, 'tmax': 8}:
        raise ValueError('Frozen end-to-end canary gate absent')
    if gate['teacher_config_sha256'] != TEACHER_SHA or gate['wheel_sha256'] != WHEEL_SHA:
        raise ValueError('Canary contract differs')
    if sha(R / 'configs/teacher-native-11tools-summary-r1.json') != TEACHER_SHA:
        raise ValueError('Frozen teacher config changed')
    if not os.environ.get('DEEPSEEK_API_KEY'):
        raise ValueError('Authorized private service credential absent')
    rows = frozen_rows()
    queue = TrialQueue(n_concurrent=8, retry_config=RetryConfig(max_retries=0))
    pending = {}
    image_materialization = asyncio.Semaphore(1)
    next_pool = 'calibforge'
    outcomes = {p.stem: read(p) for p in (S / 'environment-outcomes').glob('*.json')}
    for scope in ['collection-r3', 'collection-r2']:
        for p in (R / 'stream' / scope / 'environment-outcomes').glob('*.json'):
            value = read(p)
            if value['status'] == 'ENV_READY' and not blocking_review(p.stem):
                outcomes.setdefault(p.stem,value)
    for p in (R / 'checks/native-environment-reviews-r10').glob('*.json'):
        if not blocking_review(p.stem):
            reviewed=read(p)
            if sha(Path(reviewed['prior_outcome'])) != reviewed['prior_outcome_sha256']:
                raise ValueError('Prior native environment review source changed')
            outcomes.setdefault(p.stem, read(p))
    for p in (R / 'checks/native-reserve-acceptance-r4').glob('*.json'):
        value=read(p)
        if value['status']=='ENV_READY' and not blocking_review(p.stem):
            if sha(Path(value['raw_outcome']))!=value['raw_outcome_sha256']:
                raise ValueError('Accepted reserve native source changed')
            outcomes.setdefault(p.stem,value)
    manifest = dict(task_slot_ids=sorted(r['task_id'] for r in original_rows()),selected_manifest_sha256={name:sha(R/'manifests'/name) for name in MANIFESTS},
        native_base_config_sha256=sha(R/'configs/canary-summary-cf.json'),
        source_sha256=sha(Path(__file__)),native_concurrency=8,teacher_config_sha256=TEACHER_SHA,wheel_sha256=WHEEL_SHA,
        helper_sha256={name:sha(R/'scripts'/name) for name in ['collection_selection_r4.py','collection_readiness_r4.py','native_image_archive149_r1.py']},
        selection_policy='Original1000 frozen slots; append-only native-accepted exact-stratum source reserves before any original teacher dispatch; immutable active-selection snapshot per dispatch',
        image_storage='Exact original image ID; native Docker save/load with17 cold archive/hash/DiffID and expanded-size evidence; one materialization at a time; capacity waits are not Task failures',
        drain_policy='DRAIN_REQUESTED.json stops admission; current native lifecycles finish; no active teacher cancellation',
        network_extension='Native extra_docker_compose; unique perTask /28 in route-checked10.241.0.0/18; default NAT/public behavior; original Task bytes unchanged',
        network_capacity_proof=str(R/'checks/isolated-network-capacity-r4.json'))
    if not read(R/'checks/isolated-network-capacity-r4.json')['passed']:raise ValueError('Native Docker isolated network proof missing')
    if (S/'CAMPAIGN.json').exists():
        if read(S/'CAMPAIGN.json')!=manifest:raise ValueError('Frozen campaign identity changed')
    else:save(S/'CAMPAIGN.json',manifest)
    # Existing incomplete dispatches require native observation; never replay.
    for path in R.glob('stream/*/dispatches/*/dispatch.json'):
        item = read(path)
        if item['kind'] == 'teacher' and not (path.parents[2] / 'trials' / item['trial_name'] / 'result.json').exists():
            raise ValueError('Previously dispatched native trial needs recovery/observation, never implicit replay')

    async def resident(admitted):
        while True:
            try:
                async with image_materialization:
                    value = await asyncio.to_thread(ensure_resident, admitted)
                save(S/'image-materializations'/(admitted['task_id']+'.json'),value)
                return
            except ImageCapacityError as error:
                save(S/'image-waits'/(admitted['task_id']+'.json'),dict(task_id=admitted['task_id'],
                    status='WAITING_FOR_IMAGE_CAPACITY',reason=str(error),model_calls=0))
                if (S/'DRAIN_REQUESTED.json').exists():raise
                await asyncio.sleep(60)

    async def dispatch(row, kind):
        if kind not in ['install','nop','teacher'] or sha(R/'configs/canary-summary-cf.json')!=manifest['native_base_config_sha256']:
            raise ValueError('Frozen native base configuration changed')
        task_path=Path(row['prepared_task_path'])
        if sha(task_path/'task.toml')!=row['prepared_task_toml_sha256'] or sha(task_path/'instruction.md')!=row['instruction_sha256']:
            raise ValueError('Frozen admitted task identity changed')
        if any(sha(task_path/item['path'])!=item['sha256'] for item in row['verifier_files']):
            raise ValueError('Frozen original verifier file changed')
        config = native_config(row, kind)
        if kind == 'teacher':
            if (S/'DRAIN_REQUESTED.json').exists():raise ValueError('Admission drained before teacher dispatch')
            if sha(Path(__file__)) != manifest['source_sha256']:
                raise ValueError('Frozen controller source changed')
            if any(sha(R/'scripts'/name)!=expected for name,expected in manifest['helper_sha256'].items()):raise ValueError('Frozen admission helper changed')
            counts = attempt_counts()
            if counts[row['task_id']] >= 2 or sum(counts.values()) >= 2000:
                raise ValueError('Teacher attempt budget exhausted')
        active = frozen_rows()
        current = next(r for r in active if r['slot_id'] == row['slot_id'])
        if current['task_id'] != row['task_id']:
            raise ValueError('Sampling binding changed before dispatch; no implicit substitute')
        selection_sha = hashlib.sha256(json.dumps(active,sort_keys=True).encode()).hexdigest()
        selection = S/'selection-snapshots'/(selection_sha+'.json')
        if not selection.exists():save(selection,active)
        destination = S / 'dispatches' / str(uuid4())
        destination.mkdir(parents=True)
        (destination / 'trial-config.json').write_text(config.model_dump_json(indent=2))
        save(destination / 'dispatch.json', dict(task_id=row['task_id'], pool=row['pool'], kind=kind,
            trial_name=config.trial_name, config_sha256=sha(destination / 'trial-config.json'),
            admitted_task=row, teacher_config_sha256=TEACHER_SHA, wheel_sha256=WHEEL_SHA,
            selection_snapshot=str(selection),selection_snapshot_sha256=sha(selection),
            dispatched_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        result = await queue.submit(config)
        return result, S / 'trials' / config.trial_name

    async def process(row):
        ident = row['task_id']
        admitted = None
        try:
            admitted = prepared(row, basic_receipt(row))
            await resident(admitted)
            result, install_trial = await dispatch(admitted, 'install')
            if result.exception_info or result.infrastructure_errors:
                raise ValueError('Native CLI installation/lifecycle failed')
            result, nop_trial = await dispatch(admitted, 'nop')
            reward = verify_nop(result, nop_trial, admitted)
            outcome = dict(task_id=ident, pool=row['pool'], status='ENV_READY', admitted_task=admitted,
                native_install_trial=str(install_trial), native_nop_trial=str(nop_trial),
                nop_reward=reward, teacher_success_not_implied=True)
            save(S / 'environment-outcomes' / (ident + '.json'), outcome)
            outcomes[ident] = outcome
            # First attempts stream immediately. Previously attempted tasks wait
            # for target-level qualification before a legal second attempt.
            if attempt_counts()[ident] == 0 and not (S/'DRAIN_REQUESTED.json').exists():
                await dispatch(admitted, 'teacher')
        except Exception as error:
            outcome = dict(task_id=ident, pool=row['pool'], status='ENV_FAILED',
                error_type=type(error).__name__, reason=str(error)[:1000])
            # A failed teacher must never turn a validated environment into failed.
            if outcomes.get(ident, {}).get('status') != 'ENV_READY':
                save(S / 'environment-outcomes' / (ident + '.json'), outcome)
                outcomes[ident] = outcome
            save(S / 'errors' / (ident + '.json'), outcome)
        finally:
            if admitted is not None:
                await release_image(admitted)

    async def release_image(admitted):
        try:
            async with image_materialization:
                value=await asyncio.to_thread(release_cold_cache,admitted)
            save(S/'image-releases'/(admitted['task_id']+'.json'),value)
        except Exception as error:
            save(S/'image-releases'/(admitted['task_id']+'.json'),dict(status='CACHE_RELEASE_REFUSED',
                reason=str(error)[:800],image_id=admitted['image_id']))

    async def followup(row):
        admitted = None
        try:
            admitted = dict(outcomes[row['task_id']]['admitted_task'],slot_id=row['slot_id'])
            await resident(admitted)
            await dispatch(admitted, 'teacher')
        except Exception as error:
            save(S/'errors'/(row['task_id']+'-teacher.json'),dict(task_id=row['task_id'],
                status='TEACHER_DISPATCH_ERROR',error_type=type(error).__name__,reason=str(error)))
        finally:
            if admitted is not None:
                await release_image(admitted)

    async with asyncio.TaskGroup() as group:
        while True:
            rows = frozen_rows()
            for ident, task in list(pending.items()):
                if task.done():
                    del pending[ident]
            draining = (S/'DRAIN_REQUESTED.json').exists()
            if draining and not pending:
                save(S/'DRAINED.json',dict(status='DRAINED_WITH_NO_ACTIVE_TRIALS',pid=os.getpid(),model_calls_cancelled=0))
                return
            # Persist the alternating pool cursor even when only one slot opens.
            candidates = admission_candidates(rows,outcomes,pending,attempt_counts(),audited_second_attempts())
            while not draining and len(pending) < 8 and candidates:
                order = [next_pool, 'tmax' if next_pool=='calibforge' else 'calibforge']
                for pool in order:
                    if pool not in candidates:continue
                    if len(pending) >= 8:
                        break
                    item = next(candidates[pool], None)
                    if item is None:
                        del candidates[pool]
                    else:
                        row,kind=item
                        pending[row['task_id']] = group.create_task(followup(row) if kind=='teacher' else process(row))
                        next_pool = 'tmax' if pool=='calibforge' else 'calibforge'
            counts = attempt_counts()
            save(R / 'campaign-state.json', dict(status='DRAINING_NATIVE_TRIAL_QUEUE' if draining else 'STREAMING_NATIVE_TRIAL_QUEUE', pid=os.getpid(),campaign_scope='collection-r4',
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                native_concurrency=8, active_task_pipelines=list(pending),
                next_pool=next_pool,
                submitted_attempts=sum(counts.values()), teacher_independent_tasks=len(counts),
                environment_outcomes=dict(Counter(x['status'] for x in outcomes.values())),
                teacher_tasks_cap=1000, complete_attempts_cap=2000, per_task_attempts_cap=2,
                teacher_config_sha256=TEACHER_SHA, wheel_sha256=WHEEL_SHA,
                corpus_freeze='PENDING_ALL_TASKS_AND_TARGET_AUDITS',
                budget_authority='User1000unique/2000complete-attempt cap; no verified USD cap in frozen campaign'))
            # Keep the sole controller available while exact target audits and
            # preregistered environment recovery are outstanding. No extra calls.
            await asyncio.sleep(10)

if __name__ == '__main__':
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    async def entry():
        current = asyncio.current_task()
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, current.cancel)
        await main()
    asyncio.run(entry())
