"""Finite native install/NOP checks for the registered CF/TMax reserves only.

Uses existing Harbor TrialQueue and adapter. No teacher dispatch or active
selection-manifest mutation. Every official file and resource stays unchanged.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tomllib
from uuid import uuid4
import toml
from harbor.models.job.config import RetryConfig
from harbor.models.trial.config import TrialConfig
from harbor.models.task.config import TaskConfig
from harbor.trial.queue import TrialQueue
from native_image_archive149_r1 import load_verified_archive, image_info, SSH, HOST, PY17, E17

R = Path('/home/chenkeyi/.local/share/harbor-rsi/qwen35-new-cf500-tmax500-20261029')
S = R / ('stream/reserve-acceptance-r2' if len(sys.argv) == 2 else 'stream/reserve-acceptance-r1')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Observe the preserved original native reserve pass')
    path.write_text(json.dumps(value, indent=2))


async def main():
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Inspect any existing native diagnostic before resumption')
    planfile = Path(sys.argv[1]) if len(sys.argv) == 2 else R / 'manifests/CF_ENVIRONMENT_RESERVE_PLAN_R1.json'
    cf_plan = json.loads(planfile.read_text())
    cf = cf_plan['candidate']
    source_file = R / 'checks/cf-reserve-environments-r1' / (cf['task_id'] + '.json')
    basic = json.loads(source_file.read_text())
    if basic['status'] != 'IMAGE_IDENTITY_AND_BASIC_SETUP_PASSED' or not basic['cleanup_confirmed']:
        raise ValueError('CF reserve basic environment is not accepted')
    request = json.dumps(dict(task_id=cf['task_id'], image_id=basic['image_id'], pool='calibforge'))
    reply = subprocess.run(SSH + [HOST, shlex.join([PY17, E17 + '/scripts/resolve_cold_image17_r1.py'])],
        input=request, capture_output=True, text=True, check=True, timeout=600)
    load_verified_archive(cf['task_id'], basic['image_id'], 'calibforge', json.loads(reply.stdout))
    original = Path(cf['source_path']); prepared = R / 'prepared-tasks/calibforge-reserve-r1' / cf['task_id']
    if sha(original / 'task.toml') != cf['task_toml_sha256'] or sha(original / 'instruction.md') != cf['instruction_sha256']:
        raise ValueError('Preregistered original CF task changed')
    if not prepared.exists():
        prepared.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(original, prepared)
        task = tomllib.loads((original / 'task.toml').read_text()); task['environment']['docker_image'] = basic['image_id']
        (prepared / 'task.toml').write_text(toml.dumps(task))
    for item in cf['private_file_identities']:
        if sha(prepared / item['path']) != item['sha256']:
            raise ValueError('Original CF verifier bytes changed')
    candidates = [dict(cf, prepared_task_path=str(prepared))]
    if len(sys.argv) == 1:
        candidates.extend(map(json.loads, (R / 'manifests/TMAX_RUNTIME_REPLACEMENTS_READY_R3.jsonl').open()))
    originals = {r['task_id']: r for name in ['CALIBFORGE_500_TASKS.jsonl', 'TMAX_RUNTIME_CANDIDATES_V2.jsonl']
        for r in map(json.loads, (R / 'manifests' / name).open())}
    for row in candidates:
        old = row.get('runtime_replaced_task_id', cf_plan['replaced_task_id'])
        if row['stratum'] != originals[old]['stratum']:
            raise ValueError('Preregistered reserve differs from original exact stratum')
    freeze(S / 'PLAN.json', dict(task_ids=[x['task_id'] for x in candidates],
        selected_manifest_modifications=0, model_calls=0, teacher_attempts=0,
        reason='Original environment-only reserves, fixed rank and fixed family split', native_diagnostic_concurrency=1))
    network = R / 'configs/reserve-native-network-r1.json'
    if not network.exists():
        freeze(network, dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet='10.241.63.240/28')])))))
    base = json.loads((R / 'configs/canary-summary-cf.json').read_text())
    queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    for row in candidates:
        ident = row['task_id']; prepared = Path(row['prepared_task_path'])
        cfg = TaskConfig.model_validate(tomllib.loads((prepared / 'task.toml').read_text()))
        image = cfg.environment.docker_image
        if image_info(image) is None:
            raise ValueError('Original prepared reserve image missing; do not rebuild implicitly')
        evidence = dict(task_id=ident, pool=row['pool'], status='NATIVE_DIAGNOSTICS_STARTED',
            task_toml_sha256=sha(prepared / 'task.toml'), model_calls=0, teacher_attempts=0,
            original_verifier_timeout_sec=cfg.verifier.timeout_sec, original_resources=cfg.environment.model_dump(mode='json'))
        try:
            for kind in ['install', 'nop']:
                agent = copy.deepcopy(base['agents'][0]) if kind == 'install' else dict(name='nop')
                if kind == 'install':
                    agent['override_timeout_sec'] = max(cfg.agent.timeout_sec, 10800)
                    agent['env'] = {}  # Installation-only; never requests a model credential.
                environment = copy.deepcopy(base['environment'])
                environment['kwargs']['project_namespace'] = 'cftmaxreservesr120261030'
                environment['extra_docker_compose'] = [str(network)]
                native = TrialConfig(task={'path': str(prepared)}, trials_dir=S / 'trials', agent=agent,
                    environment=environment, verifier=base['verifier'], install_only=kind == 'install')
                directory = S / 'dispatches' / str(uuid4()); directory.mkdir(parents=True)
                (directory / 'trial-config.json').write_text(native.model_dump_json(indent=2))
                freeze(directory / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                    trial_name=native.trial_name, config_sha256=sha(directory / 'trial-config.json'), model_calls=0))
                result = await queue.submit(native)
                trial = S / 'trials' / native.trial_name
                evidence[kind + '_trial'] = str(trial)
                evidence[kind + '_result_sha256'] = sha(trial / 'result.json')
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native reserve ' + kind + ' lifecycle/installation failed')
                if kind == 'nop':
                    raw = json.loads((trial / 'result.json').read_text())
                    reward = (raw.get('verifier_result') or {}).get('rewards', {}).get('reward')
                    if reward not in (0, 1) or not (raw.get('verifier') or {}).get('finished_at'):
                        raise ValueError('Official native reserve verifier did not finish')
                    evidence['nop_reward'] = reward
            evidence['status'] = 'NATIVE_DIAGNOSTICS_COMPLETED_VERIFIER_LOG_REVIEW_PENDING'
        except Exception as error:
            evidence.update(status='RESERVE_NATIVE_ENVIRONMENT_FAILED', error_type=type(error).__name__, reason=str(error)[:1000])
        freeze(S / 'environment-outcomes' / (ident + '.json'), evidence)
        print(json.dumps(evidence), flush=True)


if __name__ == '__main__':
    os.environ['PATH'] = str(R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for key in ['DEEPSEEK_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    asyncio.run(main())
