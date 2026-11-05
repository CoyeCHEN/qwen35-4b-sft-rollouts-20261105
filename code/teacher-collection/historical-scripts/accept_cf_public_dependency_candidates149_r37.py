"""Native17 checks of two explicitly derived candidates; no Ready publication."""
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import datetime
import fcntl
import toml
import tomllib
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows


S = n.R / 'stream/cf-public-dependency-native-candidates-r37'
E17 = '/home/chenkeyi/workspace/RSI/runtime-evidence/' + n.R.name


def load_candidate(item, frozen):
    request = dict(deployment=n.NODE, helper_sha256=frozen['loader_source_sha256'],
        build_receipt=item['remote_build_receipt'], build_receipt_sha256=item['build_receipt_sha256'])
    result = subprocess.run([*n.DEPLOYMENT['ssh'], n.DEPLOYMENT['host'],
        shlex.join([n.DEPLOYMENT['python17'], E17 + '/scripts/load_cf_public_dependency_candidate17_r37.py'])],
        input=json.dumps(request), capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError(result.stderr[-2400:])
    return json.loads(result.stdout)


async def main():
    S.mkdir(exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Observe the existing native candidate checks')
    path = n.R / 'manifests/CF_PUBLIC_VERIFIER_DEPENDENCY_NATIVE_CANDIDATES_R37.json'
    plan = json.loads(path.read_text())
    if plan['deployment_config_sha256'] != n.CONFIG_SHA or plan['engine_id'] != n.NODE['engine_id']:
        raise ValueError('Candidate native deployment differs')
    source = n.R / 'checks/cf-public-verifier-dependency-source-scope-r36.json'
    if n.sha(source) != plan['source_scope149_sha256']:
        raise ValueError('Frozen official Task/source scope changed')
    original_scope = {item['task_id']:item for item in json.loads(source.read_text())['tasks']}
    frozen = dict(plan, source_plan_sha256=n.sha(path), worker_source_sha256=n.sha(Path(__file__)))
    n.freeze(S / 'PLAN.json', frozen)
    queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    rows = {row['task_id']:row for row in active_rows(attempt_counts())}
    terminal = {}

    def state(ident, stage):
        value = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            current_task_id=ident, stage=stage, planned=len(plan['tasks']), terminal=len(terminal),
            counts={status:list(terminal.values()).count(status) for status in set(terminal.values())},
            native_concurrency=1, model_calls=0, teacher_dispatches=0,
            published_current_controller_ready=0, candidate_images_retained_at_most=2)
        tmp = S / 'state.pending'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(S / 'state.json')

    for index, item in enumerate(plan['tasks']):
        ident = item['task_id']
        out = dict(task_id=ident, pool='calibforge', status='CANDIDATE_ENV_FAILED',
            official_task_or_test_changes=0, model_calls=0, teacher_dispatches=0,
            published_current_controller_ready=False, teacher_success_not_implied=True)
        try:
            if attempt_counts().get(ident, 0):
                raise ValueError('Never change the image binding of an already-attempted Task')
            base = n.prepare_identity(rows[ident])
            if base['image_id'] != item['original_image_id']:
                raise ValueError('Original published-image identity differs')
            receipt = Path(item['local_build_receipt'])
            if n.sha(receipt) != item['build_receipt_sha256']:
                raise ValueError('Candidate build receipt changed')
            candidate = json.loads(receipt.read_text())
            if candidate['task_id'] != ident or candidate['source_scope_sha256'] != plan['remote_source_scope_sha256']:
                raise ValueError('Candidate build belongs to another frozen Task scope')
            if candidate['source']['official_private_file_identities'] != original_scope[ident]['official_private_file_identities']:
                raise ValueError('Candidate source/test identities differ')
            state(ident, 'CHECKING_LINEAGE_AND_LOADING_CANDIDATE_ON_PRIVATE17')
            loaded = await asyncio.to_thread(load_candidate, item, frozen)
            n.freeze(S / 'image-lineage-and-load' / (ident + '.json'), loaded)
            if loaded['image_id'] != candidate['image_id'] or loaded['task_id'] != ident:
                raise ValueError('Loaded candidate image differs')
            original = Path(base['prepared_task_path'])
            prepared = S / 'prepared-tasks' / ident
            shutil.copytree(original, prepared)
            expected = tomllib.loads((original / 'task.toml').read_text())
            expected['environment']['docker_image'] = candidate['image_id']
            (prepared / 'task.toml').write_text(toml.dumps(expected))
            if tomllib.loads((prepared / 'task.toml').read_text()) != expected:
                raise ValueError('Candidate Task copy changed additional configuration')
            for source_file in original.rglob('*'):
                if source_file.is_file() and source_file.relative_to(original) != Path('task.toml'):
                    if n.sha(source_file) != n.sha(prepared / source_file.relative_to(original)):
                        raise ValueError('Official instruction/test member changed')
            admitted = dict(base, prepared_task_path=str(prepared),
                prepared_task_toml_sha256=n.sha(prepared / 'task.toml'), image_id=candidate['image_id'],
                original_published_image_id=base['image_id'], explicit_public_verifier_dependency_candidate=True,
                candidate_build_receipt=str(receipt), candidate_build_receipt_sha256=n.sha(receipt))
            state(ident, 'CHECKING_ORIGINAL_RESOURCES_AND_INITIAL_STATE_ON17')
            n.freeze(S / 'initial-outcomes' / (ident + '.json'), await asyncio.to_thread(n.initial, admitted))
            subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.249.0.0')) + index * 16, 28)))
            network = S / 'networks' / (ident + '.json')
            n.freeze(network, dict(networks=dict(default=dict(ipam=dict(config=[dict(subnet=subnet)])))))
            for kind in ['install', 'nop']:
                state(ident, 'NATIVE_' + kind.upper() + '_ON17')
                cfg = n.native_config(admitted, kind)
                cfg.trials_dir = S / 'trials'
                if kind == 'install':
                    cfg.agent.env = {}
                cfg.environment.extra_docker_compose = [network, *cfg.environment.extra_docker_compose[1:]]
                dispatch_dir = S / 'dispatches' / str(uuid4())
                dispatch_dir.mkdir(parents=True)
                (dispatch_dir / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(dispatch_dir / 'dispatch.json', dict(task_id=ident, pool='calibforge', kind=kind,
                    trial_name=cfg.trial_name, config_sha256=n.sha(dispatch_dir / 'trial-config.json'),
                    model_calls=0, native_candidate_acceptance_only=True))
                result = await queue.submit(cfg)
                trial = S / 'trials' / cfg.trial_name
                out['native_' + kind + '_trial'] = str(trial)
                out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                n.freeze(S / 'ssd-trial-archives' / (trial.name + '.json'), await asyncio.to_thread(n.archive_trial, trial))
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native candidate lifecycle failed: ' + str(result.exception_info))
                if kind == 'nop':
                    out['nop_reward'] = n.verify_nop(result, trial, admitted)
            if attempt_counts().get(ident, 0):
                raise ValueError('Task unexpectedly admitted during candidate preparation')
            out.update(status='NATIVE_CANDIDATE_ACCEPTED_PENDING_CONTROLLED_PROMOTION', admitted_task=admitted,
                engine_id=n.NODE['engine_id'], deployment_config_sha256=n.CONFIG_SHA,
                image_lineage_proof=str(S / 'image-lineage-and-load' / (ident + '.json')),
                promotion_requirement='New source-checked resolver/deployment must bind the derived image and preserve all original image/Task/test identities before any Ready or paid Teacher dispatch')
        except Exception as error:
            out.update(error_type=type(error).__name__, reason=str(error)[-2000:])
        finally:
            n.freeze(S / 'candidate-outcomes' / (ident + '.json'), out)
            terminal[ident] = out['status']
            state(ident, 'NATIVE_CANDIDATE_CHECK_TERMINAL')
            print(json.dumps(dict(task_id=ident, status=out['status'], reason=out.get('reason'))), flush=True)
    state(None, 'FINITE_NATIVE_PUBLIC_DEPENDENCY_CANDIDATE_ACCEPTANCE_TERMINAL')
    n.freeze(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    for key in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(key, None)
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    asyncio.run(main())
