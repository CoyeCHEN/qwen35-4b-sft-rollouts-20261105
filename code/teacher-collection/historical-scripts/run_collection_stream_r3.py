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
S = R / 'stream/collection-r3'
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

def frozen_rows():
    rows = []
    for name in ['CALIBFORGE_500_TASKS.jsonl', 'TMAX_RUNTIME_CANDIDATES_V2.jsonl']:
        rows.extend(map(json.loads, (R / 'manifests' / name).open()))
    if len(rows) != 1000 or len({r['task_id'] for r in rows}) != 1000:
        raise ValueError('Frozen unique task scope differs')
    if Counter(r['pool'] for r in rows) != {'calibforge': 500, 'tmax': 500}:
        raise ValueError('Frozen pool scope differs')
    if not set(attempt_counts()) <= {r['task_id'] for r in rows}:
        raise ValueError('An attempted task was replaced')
    families = {}
    for row in rows:
        key = row['pool'], row['family_id']
        if key in families and families[key] != row['split']:
            raise ValueError('Family crosses fixed task split')
        families[key] = row['split']
    return rows

def basic_receipt(row):
    names = (['cf-environments-oci-r5'] if row['pool'] == 'calibforge' else
        ['tmax-environments-public-input-review-r6', 'tmax-environments-collision-recheck-r5', 'tmax-environments-runtime-r4'])
    passed = {'IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED', 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING'}
    for name in names:
        path = R / 'checks' / name / (row['task_id'] + '.json')
        if path.exists():
            value = read(path)
            if value.get('status') in passed:
                if not value.get('cleanup_confirmed', value.get('preparation_container_cleanup_confirmed', False)):
                    raise ValueError('Preparation cleanup unconfirmed')
                return path, value
    return None

def prepared(row, basic):
    receipt_path, evidence = basic
    original = Path(row['source_path'] if row['pool'] == 'calibforge' else row['task_path'])
    if sha(original / 'instruction.md') != row['instruction_sha256']:
        raise ValueError('Frozen instruction changed')
    if row['pool'] == 'calibforge':
        if sha(original / 'task.toml') != row['task_toml_sha256']:
            raise ValueError('Frozen original task config changed')
        source = tomllib.loads((original / 'task.toml').read_text())
        source['environment']['docker_image'] = evidence['image_id']
        path = R / 'prepared-tasks/calibforge-pinned-stream-r1' / row['task_id']
        if not path.exists():
            shutil.copytree(original, path)
            (path / 'task.toml').write_text(toml.dumps(source))
        if tomllib.loads((path / 'task.toml').read_text()) != source:
            raise ValueError('External image pin copy changed')
        identities = row['private_file_identities']
    else:
        path = Path(evidence['prepared_task_path'])
        if sha(path / 'task.toml') != evidence['prepared_task_toml_sha256']:
            raise ValueError('Prepared native task config changed')
        identities = [dict(path=str(p.relative_to(original)), sha256=sha(p)) for p in sorted((original / 'tests').rglob('*')) if p.is_file()]
    for item in identities:
        if sha(path / item['path']) != item['sha256']:
            raise ValueError('Official verifier/private bytes changed')
    native = NativeTaskConfig.model_validate(tomllib.loads((path / 'task.toml').read_text()))
    source_native = NativeTaskConfig.model_validate(tomllib.loads((original / 'task.toml').read_text()))
    for key in ['cpus', 'memory_mb', 'storage_mb', 'gpus']:
        if getattr(native.environment, key) != getattr(source_native.environment, key):
            raise ValueError('Original task resources changed')
    if native.verifier != source_native.verifier:
        raise ValueError('Original verifier configuration changed')
    if row['pool'] == 'tmax' and (native.environment.workdir != '/home/user' or native.environment.env.get('HOME') != '/home/user'):
        raise ValueError('Original TMax directory contract differs')
    return dict(**row, prepared_task_path=str(path), prepared_task_toml_sha256=sha(path / 'task.toml'),
        image_id=evidence['image_id'], preparation_receipt=str(receipt_path), preparation_receipt_sha256=sha(receipt_path),
        agent_timeout_override_sec=max(source_native.agent.timeout_sec, 10800),
        original_verifier_timeout_sec=native.verifier.timeout_sec, verifier_files=identities)

def native_config(row, kind):
    base = read(R / 'configs/canary-summary-cf.json')
    agent = copy.deepcopy(base['agents'][0])
    agent['override_timeout_sec'] = row['agent_timeout_override_sec']
    if kind == 'nop':
        agent = {'name': 'nop'}
    env = copy.deepcopy(base['environment'])
    env['kwargs']['project_namespace'] = 'cftmaxstreamr320261030'
    all_ids = sorted(r['task_id'] for r in frozen_rows())
    subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.241.0.0')) + all_ids.index(row['task_id']) * 16, 28)))
    override = R / 'configs/stream-task-networks-r3' / (row['task_id'] + '.json')
    value = dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)]))))
    if override.exists():
        if read(override) != value:raise ValueError('Frozen per-task network override changed')
    else:
        override.parent.mkdir(parents=True,exist_ok=True)
        with override.open('x') as stream:stream.write(json.dumps(value,indent=2))
    env['extra_docker_compose'] = [str(override)]
    return TrialConfig(task={'path': row['prepared_task_path']}, trials_dir=S / 'trials',
        agent=agent, environment=env, verifier=base['verifier'], install_only=kind == 'install')

def verify_nop(result, trial):
    if result.exception_info or result.infrastructure_errors:
        raise ValueError('Native NOP verifier/lifecycle infrastructure failure')
    raw = read(trial / 'result.json')
    reward = (raw.get('verifier_result') or {}).get('rewards', {}).get('reward')
    if not (raw.get('verifier') or {}).get('finished_at') or reward not in (0, 1):
        raise ValueError('Native official verifier did not complete with valid reward')
    text = '\n'.join(p.read_text(errors='replace') for p in (trial / 'verifier').glob('test-*.txt'))
    fatal = ['ERROR collecting', 'ModuleNotFoundError:', 'ImportError while importing', 'command not found', 'No module named pytest']
    if any(value in text for value in fatal):
        raise ValueError('Official verifier dependency/startup error in raw logs')
    return reward

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
    outcomes = {p.stem: read(p) for p in (S / 'environment-outcomes').glob('*.json')}
    for p in (R / 'stream/collection-r2/environment-outcomes').glob('*.json'):
        value = read(p)
        if value['status'] == 'ENV_READY' and attempt_counts()[p.stem] > 0:
            outcomes.setdefault(p.stem,value)
    manifest = dict(task_ids=sorted(r['task_id'] for r in rows),selected_manifest_sha256={name:sha(R/'manifests'/name) for name in ['CALIBFORGE_500_TASKS.jsonl','TMAX_RUNTIME_CANDIDATES_V2.jsonl']},
        source_sha256=sha(Path(__file__)),native_concurrency=8,teacher_config_sha256=TEACHER_SHA,wheel_sha256=WHEEL_SHA,
        network_extension='Native extra_docker_compose; unique perTask /28 in route-checked10.241.0.0/18; default NAT/public behavior; original Task bytes unchanged',
        network_capacity_proof=str(R/'checks/isolated-network-capacity-r4.json'))
    if not read(R/'checks/isolated-network-capacity-r4.json')['passed']:raise ValueError('Native Docker isolated network proof missing')
    if (S/'CAMPAIGN.json').exists():
        if read(S/'CAMPAIGN.json')!=manifest:raise ValueError('Frozen campaign identity changed')
    else:save(S/'CAMPAIGN.json',manifest)
    # Existing incomplete dispatches require native observation; never replay.
    for path in S.glob('dispatches/*/dispatch.json'):
        item = read(path)
        if not (S / 'trials' / item['trial_name'] / 'result.json').exists():
            raise ValueError('Previously dispatched native trial needs recovery/observation, never implicit replay')

    async def dispatch(row, kind):
        config = native_config(row, kind)
        if kind == 'teacher':
            counts = attempt_counts()
            if counts[row['task_id']] >= 2 or sum(counts.values()) >= 2000:
                raise ValueError('Teacher attempt budget exhausted')
        destination = S / 'dispatches' / str(uuid4())
        destination.mkdir(parents=True)
        (destination / 'trial-config.json').write_text(config.model_dump_json(indent=2))
        save(destination / 'dispatch.json', dict(task_id=row['task_id'], pool=row['pool'], kind=kind,
            trial_name=config.trial_name, config_sha256=sha(destination / 'trial-config.json'),
            admitted_task=row, teacher_config_sha256=TEACHER_SHA, wheel_sha256=WHEEL_SHA,
            dispatched_at=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        result = await queue.submit(config)
        return result, S / 'trials' / config.trial_name

    async def process(row):
        ident = row['task_id']
        try:
            admitted = prepared(row, basic_receipt(row))
            result, install_trial = await dispatch(admitted, 'install')
            if result.exception_info or result.infrastructure_errors:
                raise ValueError('Native CLI installation/lifecycle failed')
            result, nop_trial = await dispatch(admitted, 'nop')
            reward = verify_nop(result, nop_trial)
            outcome = dict(task_id=ident, pool=row['pool'], status='ENV_READY', admitted_task=admitted,
                native_install_trial=str(install_trial), native_nop_trial=str(nop_trial),
                nop_reward=reward, teacher_success_not_implied=True)
            save(S / 'environment-outcomes' / (ident + '.json'), outcome)
            outcomes[ident] = outcome
            # First attempts stream immediately. Previously attempted tasks wait
            # for target-level qualification before a legal second attempt.
            if attempt_counts()[ident] == 0:
                await dispatch(admitted, 'teacher')
        except Exception as error:
            outcome = dict(task_id=ident, pool=row['pool'], status='ENV_FAILED',
                error_type=type(error).__name__, reason=str(error)[:1000])
            # A failed teacher must never turn a validated environment into failed.
            if outcomes.get(ident, {}).get('status') != 'ENV_READY':
                save(S / 'environment-outcomes' / (ident + '.json'), outcome)
                outcomes[ident] = outcome
            save(S / 'errors' / (ident + '.json'), outcome)

    async def followup(row):
        try:
            await dispatch(outcomes[row['task_id']]['admitted_task'], 'teacher')
        except Exception as error:
            save(S/'errors'/(row['task_id']+'-teacher.json'),dict(task_id=row['task_id'],
                status='TEACHER_DISPATCH_ERROR',error_type=type(error).__name__,reason=str(error)))

    async with asyncio.TaskGroup() as group:
        while True:
            for ident, task in list(pending.items()):
                if task.done():
                    del pending[ident]
            # Alternate available pools, filling all8 if just one is ready.
            candidates = {pool: iter([r for r in rows if r['pool'] == pool
                and r['task_id'] not in pending and r['task_id'] not in outcomes
                and basic_receipt(r) is not None]) for pool in ['calibforge', 'tmax']}
            while len(pending) < 8 and candidates:
                for pool in list(candidates):
                    if len(pending) >= 8:
                        break
                    row = next(candidates[pool], None)
                    if row is None:
                        del candidates[pool]
                    else:
                        pending[row['task_id']] = group.create_task(process(row))
            # First success stops immediately; actual qualification controls retry.
            # Existing native queue still owns every attempt and concurrency slot.
            counts=attempt_counts()
            second=audited_second_attempts()
            for row in rows:
                if len(pending)>=8:break
                ident=row['task_id']
                if ident in pending or outcomes.get(ident,{}).get('status')!='ENV_READY':continue
                if counts[ident]==0 or (counts[ident]==1 and ident in second):
                    pending[ident]=group.create_task(followup(row))
            counts = attempt_counts()
            save(R / 'campaign-state.json', dict(status='STREAMING_NATIVE_TRIAL_QUEUE', pid=os.getpid(),
                checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                native_concurrency=8, active_task_pipelines=list(pending),
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
