"""Finite original initial-state and native CLI/NOP acceptance of one reserve.

No builds, model calls, source edits or teacher retry. A binding is published
only after all original checks complete, with the original failure retained.
"""
import asyncio
from collections import Counter
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tomllib
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.models.task.config import TaskConfig
from harbor.trial.queue import TrialQueue
import run_collection_stream_r4 as contract
from collection_readiness_r4 import prepared, release_cold_cache, verify_nop
from collection_selection_r4 import active_rows, original_rows
from native_image_archive149_r1 import SSH, HOST, PY17, E17, load_verified_archive, image_info
from tmax_runtime_adapter import runtime_compose_override

R = contract.R
S = R / 'stream/tmax-initial-reserve-acceptance-r5'
MANIFEST_SHA = '7a3d0c4b27f042aa52a55b943102c9cb9a2cde0eb29034a5690160a15d98a197'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2))


def run(args, timeout=180):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def validate_binding(plan, row):
    counts = contract.attempt_counts()
    old = plan['replaced_task_id']
    if counts.get(old, 0) or counts.get(row['task_id'], 0):
        raise ValueError('Source/candidate already attempted; no replacement')
    rows = active_rows(counts)
    selected = next(x for x in rows if x['slot_id'] == old)
    if selected['task_id'] != old or any(x['task_id'] == row['task_id'] for x in rows):
        raise ValueError('Original slot already bound or candidate already selected')
    for key in ['pool', 'stratum', 'split']:
        if selected[key] != row[key]:
            raise ValueError('Preregistered exact stratum differs: ' + key)
    reserve = R / 'manifests/TMAX_RESERVES.jsonl'
    if sha(reserve) != plan['preregistered_reserves_sha256']:
        raise ValueError('Frozen reserve universe changed')
    registered = next(x for x in map(json.loads, reserve.open()) if x['task_id'] == row['task_id'])
    for key, value in registered.items():
        if key == 'task_path':
            if Path(row[key]) != R / 'tasks/tmax' / row['task_id']:
                raise ValueError('Native converted task path changed')
        elif row.get(key) != value:
            raise ValueError('Preregistered metadata changed: ' + key)
    proposed = [dict(row, slot_id=old) if x['slot_id'] == old else x for x in rows]
    families = {}
    for item in proposed:
        family = item['family_id']
        if family in families and families[family] != item['split']:
            raise ValueError('Fixed family split crosses after binding')
        families[family] = item['split']
    if row['exclusion_reasons'] or len({x['task_id'] for x in proposed}) != 1000:
        raise ValueError('Exclusion or unique task scope changed')
    failure = Path(plan['source_environment_failure'])
    if sha(failure) != plan['source_environment_failure_sha256']:
        raise ValueError('Original failure identity changed')
    return proposed


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    planfile = R / 'manifests/TMAX_INITIAL_STATE_RESERVE_PLAN_R5.json'
    source_manifest = R / 'manifests/TMAX_INITIAL_STATE_RESERVE_CANDIDATE_R5.jsonl'
    if sha(source_manifest) != MANIFEST_SHA:
        raise ValueError('Frozen candidate manifest changed')
    plan = read(planfile)
    row, = map(json.loads, source_manifest.open())
    proposed = validate_binding(plan, row)
    freeze(S / 'PLAN.json', dict(task_id=row['task_id'], slot_id=plan['replaced_task_id'],
        source_plan_sha256=sha(planfile), source_manifest_sha256=MANIFEST_SHA,
        source_sha256=sha(Path(__file__)), model_calls=0, native_concurrency=1,
        teacher_dispatches=0, original_task_modifications=0))
    ident = row['task_id']
    outcome = dict(task_id=ident, pool='tmax', status='ENV_FAILED', model_calls=0, teacher_attempts=0)
    admitted = None
    try:
        request = json.dumps(dict(task_id=ident, pool='tmax'))
        # Resolve the exact original native OCI image, never implicitly build.
        built_path = '/ssd/chenkeyi/' + R.name + '/buildkit-rootless-r2/archives/' + ident + '/client-proxy-r3/build.json'
        reply = run(SSH + [HOST, 'cat ' + shlex.quote(built_path)])
        reply.check_returncode()
        built = json.loads(reply.stdout)
        freeze(S / 'original-build-receipt.json', built)
        if built['status'] != 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING' or built['source_context']['source_manifest_sha256'] != MANIFEST_SHA:
            raise ValueError('Original candidate build not accepted')
        image = built['native_manifest_digest']
        request = json.dumps(dict(task_id=ident, image_id=image, pool='tmax'))
        resolved = subprocess.run(SSH + [HOST, shlex.join([PY17, E17 + '/scripts/resolve_cold_image17_r1.py'])],
            input=request, capture_output=True, text=True, check=True, timeout=1800)
        cold = json.loads(resolved.stdout)
        freeze(S / 'cold-image-identity.json', cold)
        restore = await asyncio.to_thread(load_verified_archive, ident, image, 'tmax', cold)
        freeze(S / 'native-restore.json', restore)
        source = Path(row['task_path'])
        native = TaskConfig.model_validate(tomllib.loads((source / 'task.toml').read_text()))
        if sha(source / 'task.toml') != built['source_context']['source_task_toml_sha256']:
            raise ValueError('Native original task identity changed')
        initial = R / 'sources/tmax/original-tasks' / ident / 'test_initial_state.py'
        expected = next(x['sha256'] for x in row['private_file_identities'] if x['path'] == 'test_initial_state.py')
        if sha(initial) != expected or native.environment.gpus:
            raise ValueError('Original initial test changed or unsupported GPU')
        startup = runtime_compose_override(initial.parent)
        command = startup['services']['main']['command']
        command = [*command[:-1], command[-1].replace('$$', '$')]
        name = 'rsi-tmax-initial-reserve-r5-' + hashlib.sha256(ident.encode()).hexdigest()[:12]
        basic = dict(task_id=ident, pool='tmax', image_id=image, model_calls=0,
            initial_test_sha256=expected, native_startup_override=startup, source_manifest_sha256=MANIFEST_SHA,
            original_resources=native.environment.model_dump(mode='json'), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            created = run(['docker', 'create', '--name', name, '--runtime', 'runc', '--label', 'rsi.campaign=' + R.name,
                '--cpus', str(native.environment.cpus), '--memory', str(native.environment.memory_mb * 1024**2),
                '--workdir', '/home/user', '--env', 'HOME=/home/user',
                '--mount', 'type=bind,src=' + str(initial) + ',dst=/trusted-preparation/test_initial_state.py,readonly',
                '--entrypoint', '/bin/bash', image, *command[1:]])
            created.check_returncode()
            inspected = run(['docker', 'inspect', name]); inspected.check_returncode()
            actual = json.loads(inspected.stdout)[0]['HostConfig']
            if actual['Privileged'] or actual.get('DeviceRequests') or actual['Memory'] != native.environment.memory_mb * 1024**2 or actual['NanoCpus'] != round(native.environment.cpus * 10**9):
                raise ValueError('Actual native resources differ')
            run(['docker', 'start', name]).check_returncode()
            if 'healthcheck' in startup['services']['main']:
                run(['docker', 'exec', name, 'bash', '-c', 'for ((i=0; i<120; i++)); do read -r task_process < /proc/1/comm; if test "$task_process" = sleep; then exit 0; fi; sleep 1; done; exit 1'], timeout=150).check_returncode()
            probe = 'set -eu; pwd -P; id; test "$HOME" = /home/user; test "$(pwd -P)" = /home/user; test -w .; test ! -e /tests; python3 -m pytest -q /trusted-preparation/test_initial_state.py'
            checked = run(['docker', 'exec', '--workdir', '/home/user', '--env', 'HOME=/home/user', name, 'bash', '-lc', probe])
            stdout = S / 'initial-state-stdout.txt'; stderr = S / 'initial-state-stderr.txt'
            stdout.write_text(checked.stdout); stderr.write_text(checked.stderr)
            basic.update(status='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING' if checked.returncode == 0 else 'ORIGINAL_INITIAL_STATE_TEST_FAILED',
                initial_state_returncode=checked.returncode,
                initial_state_stdout_path=str(stdout), initial_state_stdout_sha256=sha(stdout),
                initial_state_stderr_path=str(stderr), initial_state_stderr_sha256=sha(stderr),
                actual_memory_bytes=actual['Memory'], actual_nano_cpus=actual['NanoCpus'])
        finally:
            cleaned = run(['docker', 'rm', '-f', name])
            basic['cleanup_confirmed'] = cleaned.returncode == 0 or 'No such container' in cleaned.stderr
            freeze(S / 'original-initial-state.json', basic)
        if basic.get('status') != 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING' or not basic['cleanup_confirmed']:
            raise ValueError('Original initial state or cleanup did not pass; preserve raw outputs')
        admitted = prepared(dict(row, slot_id=plan['replaced_task_id']), (S / 'original-initial-state.json', basic))
        contract.S = S
        queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
        for kind in ['install', 'nop']:
            cfg = contract.native_config(admitted, kind)
            cfg.environment.kwargs['project_namespace'] = 'cftmaxreserver520261030'
            if kind == 'install':
                cfg.agent.env = {}
            dispatch = S / 'dispatches' / str(uuid4()); dispatch.mkdir(parents=True)
            (dispatch / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
            freeze(dispatch / 'dispatch.json', dict(task_id=ident, pool='tmax', kind=kind,
                trial_name=cfg.trial_name, config_sha256=sha(dispatch / 'trial-config.json'), model_calls=0))
            result = await queue.submit(cfg)
            trial = S / 'trials' / cfg.trial_name
            outcome[kind + '_trial'] = str(trial)
            outcome[kind + '_result_sha256'] = sha(trial / 'result.json')
            if result.exception_info or result.infrastructure_errors:
                raise ValueError('Native ' + kind + ' lifecycle failed')
            if kind == 'nop':
                outcome['nop_reward'] = verify_nop(result, trial, admitted)
                outcome['original_verifier_logs'] = [dict(path=str(p), sha256=sha(p)) for p in (trial / 'verifier').glob('test-*.txt')]
        outcome.update(status='ENV_READY', admitted_task=admitted, teacher_success_not_implied=True)
    except Exception as error:
        outcome.update(error_type=type(error).__name__, reason=str(error)[:1200])
    finally:
        try:
            if 'image' in locals() and image_info(image) is not None:
                freeze(S / 'native-image-release.json', await asyncio.to_thread(release_cold_cache,
                    admitted or dict(row, image_id=image)))
        except Exception as error:
            freeze(S / 'native-image-release-error.json', dict(reason=str(error)[:1000]))
        raw = S / 'environment-outcomes' / (ident + '.json')
        freeze(raw, outcome)
    if outcome['status'] != 'ENV_READY':
        print(json.dumps(outcome), flush=True)
        return
    proof = R / 'checks/native-reserve-acceptance-r4' / (ident + '.json')
    freeze(proof, dict(outcome, kind='REGISTERED_SOURCE_RESERVE_NATIVE_ACCEPTANCE',
        raw_outcome=str(raw), raw_outcome_sha256=sha(raw)))
    # No canonical ready receipt or active slot is exposed during diagnostics.
    validate_binding(plan, row)
    canonical = R / 'checks/tmax-environments-preregistered-reserve-r3' / (ident + '.json')
    freeze(canonical, dict(basic, native_acceptance_proof=str(proof), native_acceptance_proof_sha256=sha(proof)))
    binding = dict(kind='REGISTERED_SOURCE_ENVIRONMENT_REPLACEMENT', replaced_task_id=plan['replaced_task_id'],
        candidate_row=row, teacher_attempts_before_replacement=0,
        native_environment_proof=str(proof), native_environment_proof_sha256=sha(proof),
        source_environment_failure=plan['source_environment_failure'], source_environment_failure_sha256=plan['source_environment_failure_sha256'],
        preregistered_reserves_sha256=plan['preregistered_reserves_sha256'], original_manifests_modified=False,
        replacement_reason=plan['reason'], preregistered_plan_sha256=sha(planfile))
    validate_binding(plan, row)
    freeze(R / 'manifests/runtime-bindings-r4' / (plan['replaced_task_id'] + '.json'), binding)
    rows = active_rows(contract.attempt_counts())
    def distribution(values):
        return {pool: dict(unique_tasks=len([x for x in values if x['pool'] == pool]),
            **{key: dict(Counter(v for x in values if x['pool'] == pool for v in (x[key] if key == 'skills' else [x[key]])))
               for key in ['coarse_category', 'split', 'native_category', 'native_difficulty', 'skills', 'family_id']})
            for pool in ['calibforge', 'tmax']}
    freeze(R / 'manifests/SAMPLING_ACTIVE_BINDINGS_R5.json', dict(original_slots=1000,
        new_binding=binding, original=distribution(original_rows()), active=distribution(rows),
        binding_identities=[dict(path=str(p), sha256=sha(p)) for p in sorted((R / 'manifests/runtime-bindings-r4').glob('*.json'))],
        same_label_does_not_claim_same_distribution=True, original_manifests_modified=False))
    print(json.dumps(dict(status='NATIVE_ACCEPTED_AND_EXACT_STRATUM_SLOT_BOUND', task_id=ident, model_calls=0)), flush=True)


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
