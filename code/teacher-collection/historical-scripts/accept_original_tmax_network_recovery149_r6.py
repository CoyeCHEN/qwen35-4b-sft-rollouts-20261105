"""Accept the original APT502-recovered task without replacing its identity."""
import asyncio
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
from native_image_archive149_r1 import SSH, HOST, PY17, E17, load_verified_archive, image_info
from tmax_runtime_adapter import runtime_compose_override

R = contract.R
S = R / 'stream/tmax-original-network-recovery-r6'
IDENT = 'task_009921_1b294fdc'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2))


def run(args, timeout=180):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    row = next(x for x in contract.original_rows() if x['task_id'] == IDENT)
    if contract.attempt_counts().get(IDENT, 0):
        raise ValueError('Already attempted original task; inspect before environment work')
    freeze(S / 'PLAN.json', dict(task_id=IDENT, model_calls=0, teacher_dispatches=0,
        source_sha256=sha(Path(__file__)), original_task_replaced=False,
        source_manifest_sha256=sha(R / 'manifests/TMAX_RUNTIME_CANDIDATES_V2.jsonl'),
        original_task_modifications=0, native_concurrency=1, native_retry=0))
    built_path = '/ssd/chenkeyi/' + R.name + '/buildkit-rootless-r2/archives/' + IDENT + '/network-recovery-r5/build.json'
    reply = run(SSH + [HOST, 'cat ' + shlex.quote(built_path)]); reply.check_returncode()
    built = json.loads(reply.stdout)
    freeze(S / 'original-network-recovery-build.json', built)
    if built['status'] != 'ORIGINAL_NATIVE_OCI_ARCHIVE_BUILT_INITIAL_AND_VERIFIER_TESTS_PENDING':
        raise ValueError('Original context recovery build is not verified')
    image = built['native_manifest_digest']
    row = dict(row, slot_id=IDENT)
    outcome = dict(task_id=IDENT, pool='tmax', status='ENV_FAILED', model_calls=0,
        teacher_attempts=0, original_task_replaced=False)
    admitted = None
    basic = None
    try:
        request = json.dumps(dict(task_id=IDENT, image_id=image, pool='tmax'))
        reply = subprocess.run(SSH + [HOST, shlex.join([PY17, E17 + '/scripts/resolve_cold_image17_r1.py'])],
            input=request, capture_output=True, text=True, check=True, timeout=1800)
        cold = json.loads(reply.stdout); freeze(S / 'cold-image-identity.json', cold)
        freeze(S / 'native-restore.json', await asyncio.to_thread(load_verified_archive, IDENT, image, 'tmax', cold))
        original = Path(row['task_path'])
        if sha(original / 'task.toml') != built['source_context']['source_task_toml_sha256']:
            raise ValueError('Original native task configuration changed')
        cfg = TaskConfig.model_validate(tomllib.loads((original / 'task.toml').read_text()))
        initial = R / 'sources/tmax/original-tasks' / IDENT / 'test_initial_state.py'
        expected = next(x['sha256'] for x in row['private_file_identities'] if x['path'] == 'test_initial_state.py')
        if sha(initial) != expected or cfg.environment.gpus:
            raise ValueError('Original initial test changed or unaccepted GPU required')
        startup = runtime_compose_override(initial.parent)
        command = startup['services']['main']['command']
        command = [*command[:-1], command[-1].replace('$$', '$')]
        name = 'rsi-tmax-network-recovery-r6-' + hashlib.sha256(IDENT.encode()).hexdigest()[:12]
        basic = dict(task_id=IDENT, pool='tmax', image_id=image, model_calls=0,
            initial_test_sha256=expected, native_startup_override=startup,
            original_resources=cfg.environment.model_dump(mode='json'),
            original_failed_build=built['original_failure'], original_failed_build_sha256=built['original_failure_sha256'],
            recovery_build_receipt=built_path, checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            kind='ORIGINAL_TASK_NETWORK_RECOVERY_NO_SAMPLING_REPLACEMENT')
        try:
            run(['docker', 'create', '--name', name, '--runtime', 'runc', '--label', 'rsi.campaign=' + R.name,
                '--cpus', str(cfg.environment.cpus), '--memory', str(cfg.environment.memory_mb * 1024**2),
                '--workdir', '/home/user', '--env', 'HOME=/home/user',
                '--mount', 'type=bind,src=' + str(initial) + ',dst=/trusted-preparation/test_initial_state.py,readonly',
                '--entrypoint', '/bin/bash', image, *command[1:]]).check_returncode()
            inspected = run(['docker', 'inspect', name]); inspected.check_returncode()
            actual = json.loads(inspected.stdout)[0]['HostConfig']
            if actual['Privileged'] or actual.get('DeviceRequests') or actual['Memory'] != cfg.environment.memory_mb * 1024**2 or actual['NanoCpus'] != round(cfg.environment.cpus * 10**9):
                raise ValueError('Native resources differ from the original task')
            run(['docker', 'start', name]).check_returncode()
            if 'healthcheck' in startup['services']['main']:
                run(['docker', 'exec', name, 'bash', '-c', 'for ((i=0; i<120; i++)); do read -r task_process < /proc/1/comm; if test "$task_process" = sleep; then exit 0; fi; sleep 1; done; exit 1'], timeout=150).check_returncode()
            probe = 'set -eu; pwd -P; id; test "$HOME" = /home/user; test "$(pwd -P)" = /home/user; test -w .; test ! -e /tests; python3 -m pytest -q /trusted-preparation/test_initial_state.py'
            checked = run(['docker', 'exec', '--workdir', '/home/user', '--env', 'HOME=/home/user', name, 'bash', '-lc', probe])
            stdout = S / 'initial-state-stdout.txt'; stderr = S / 'initial-state-stderr.txt'
            stdout.write_text(checked.stdout); stderr.write_text(checked.stderr)
            basic.update(status='IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING' if checked.returncode == 0 else 'ORIGINAL_INITIAL_STATE_TEST_FAILED',
                initial_state_returncode=checked.returncode, initial_state_stdout_path=str(stdout), initial_state_stdout_sha256=sha(stdout),
                initial_state_stderr_path=str(stderr), initial_state_stderr_sha256=sha(stderr),
                actual_memory_bytes=actual['Memory'], actual_nano_cpus=actual['NanoCpus'])
        finally:
            cleanup = run(['docker', 'rm', '-f', name])
            basic['cleanup_confirmed'] = cleanup.returncode == 0 or 'No such container' in cleanup.stderr
            freeze(S / 'original-initial-state.json', basic)
        if basic.get('status') != 'IMAGE_AND_ORIGINAL_INITIAL_STATE_PASSED_FINAL_VERIFIER_PENDING' or not basic['cleanup_confirmed']:
            raise ValueError('Original initial state or cleanup failed; preserve all raw records')
        admitted = prepared(row, (S / 'original-initial-state.json', basic))
        contract.S = S
        queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
        for kind in ['install', 'nop']:
            config = contract.native_config(admitted, kind)
            config.environment.kwargs['project_namespace'] = 'cftmaxnetworkrecoveryr620261030'
            if kind == 'install':config.agent.env = {}
            dispatch = S / 'dispatches' / str(uuid4()); dispatch.mkdir(parents=True)
            (dispatch / 'trial-config.json').write_text(config.model_dump_json(indent=2))
            freeze(dispatch / 'dispatch.json', dict(task_id=IDENT, pool='tmax', kind=kind,
                trial_name=config.trial_name, config_sha256=sha(dispatch / 'trial-config.json'), model_calls=0))
            result = await queue.submit(config)
            trial = S / 'trials' / config.trial_name
            outcome[kind + '_trial'] = str(trial); outcome[kind + '_result_sha256'] = sha(trial / 'result.json')
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
            if image_info(image) is not None:
                freeze(S / 'native-image-release.json', await asyncio.to_thread(release_cold_cache, admitted or dict(row, image_id=image)))
        except Exception as error:
            freeze(S / 'native-image-release-error.json', dict(reason=str(error)[:1000]))
        raw = S / 'environment-outcomes' / (IDENT + '.json'); freeze(raw, outcome)
    if outcome['status'] == 'ENV_READY':
        proof = R / 'checks/native-reserve-acceptance-r4' / (IDENT + '.json')
        freeze(proof, dict(outcome, kind='ORIGINAL_SELECTED_TASK_NETWORK_RECOVERY_NATIVE_ACCEPTANCE',
            raw_outcome=str(raw), raw_outcome_sha256=sha(raw)))
        # Existing r4 readiness interface; r3 does not read this directory.
        freeze(R / 'checks/tmax-environments-preregistered-reserve-r3' / (IDENT + '.json'),
            dict(basic, native_acceptance_proof=str(proof), native_acceptance_proof_sha256=sha(proof)))
    print(json.dumps(dict(task_id=IDENT, status=outcome['status'], reason=outcome.get('reason'),
        model_calls=0, original_task_replaced=False)), flush=True)


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN', 'OPENAI_API_KEY']:os.environ.pop(key, None)
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
