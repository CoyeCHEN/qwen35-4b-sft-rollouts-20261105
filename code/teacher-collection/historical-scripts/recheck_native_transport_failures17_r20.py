"""One finite zero-model native recheck of identified pre-dispatch failures.

Keep original failures and all research inputs. Use existing RemoteDocker and
TrialQueue, original deadlines/resources, one additional preparation slot.
"""
import asyncio
import datetime
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
import collection_readiness_r7 as n
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows

S = n.R / 'stream/native-transport-recheck17-r20'
ALLOWED_TYPES = {'AgentSetupTimeoutError', 'EnvironmentStartTimeoutError', 'AddTestsDirError'}
PROBE_MESSAGE = 'Task workdir probe timed out after 30 seconds before command dispatch'


def plan():
    counts = attempt_counts()
    selected = {x['task_id']: x for x in active_rows(counts)}
    ready = set()
    roots = [n.D, n.R / 'stream/collection-r4/deployment-r8']
    failed = {}
    for root in roots:
        for p in (root / 'environment-failures').glob('*.json'):
            failed[p.stem] = p
        for p in [*(root / 'environment-outcomes').glob('*.json'), *(root / 'ready-revisions').glob('*/*.json')]:
            value = json.loads(p.read_text())
            if value['status'] == 'ENV_READY':
                ready.add(value['task_id'])
    eligible = {}
    for p in (n.R / 'stream/collection-r4/dispatches').glob('*/dispatch.json'):
        dispatch = json.loads(p.read_text())
        ident = dispatch.get('task_id')
        if ident not in selected or ident not in failed or ident in ready or counts.get(ident, 0) or n.blocking_review(ident):
            continue
        if dispatch['kind'] not in ['install', 'nop']:
            continue
        cfg_path = p.parent / 'trial-config.json'
        cfg = json.loads(cfg_path.read_text())
        if cfg['environment']['kwargs'] != n.DEPLOYMENT['environment']['kwargs']:
            continue
        result_path = n.R / 'stream/collection-r4/trials' / dispatch['trial_name'] / 'result.json'
        if not result_path.exists():
            continue
        result = json.loads(result_path.read_text())
        error = result.get('exception_info') or {}
        if error.get('exception_type') not in ALLOWED_TYPES and not (
            error.get('exception_type') == 'RemoteDockerError' and error.get('exception_message') == PROBE_MESSAGE
        ):
            continue
        if n.sha(cfg_path) != dispatch['config_sha256'] or not result.get('finished_at'):
            raise ValueError('Original native failure identity changed')
        eligible[ident] = dict(task_id=ident, pool=selected[ident]['pool'],
            original_failure=str(failed[ident]), original_failure_sha256=n.sha(failed[ident]),
            original_result=str(result_path), original_result_sha256=n.sha(result_path),
            original_config=str(cfg_path), original_config_sha256=n.sha(cfg_path),
            exception_type=error['exception_type'], exception_message=error['exception_message'])
    tasks = sorted(eligible.values(), key=lambda x: x['task_id'])
    if not tasks or len(tasks) > 16:
        raise ValueError('Unexpected finite native recovery scope')
    return dict(tasks=tasks, source_sha256=n.sha(Path(__file__)),
        model_calls=0, teacher_dispatches=0, native_concurrency=1, native_retry_max=0,
        total_environment_rechecks_per_selected_task=1, node='17', engine_id=n.NODE['engine_id'],
        deployment_config_sha256=n.CONFIG_SHA,
        research_contract_changes=0, original_failures_preserved=True,
        preparation_capacity='One bounded extra zero-model slot alongside the existing bounded readiness and cold-build preparation')


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Inspect the preserved native recovery; never replay automatically')
    frozen = plan()
    n.freeze(S / 'PLAN.json', frozen)
    queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    terminal = {}

    def state(ident, stage):
        value = dict(pid=os.getpid(), checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            planned=len(frozen['tasks']), terminal=len(terminal), current_task_id=ident, stage=stage,
            native_concurrency=1, model_calls=0, teacher_dispatches=0,
            counts={status:list(terminal.values()).count(status) for status in set(terminal.values())})
        tmp = S / 'state.tmp'
        tmp.write_text(json.dumps(value, indent=2))
        tmp.replace(S / 'state.json')

    for index, item in enumerate(frozen['tasks']):
        ident = item['task_id']
        out = dict(task_id=ident, pool=item['pool'], status='ENV_FAILED',
            model_calls=0, teacher_dispatches=0, original_failure=item,
            original_task_or_tests_modified=False, teacher_success_not_implied=True)
        admitted = None
        try:
            if attempt_counts().get(ident, 0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED', reason='No recheck after teacher reservation')
                continue
            for key in ['original_failure', 'original_result', 'original_config']:
                if n.sha(Path(item[key])) != item[key + '_sha256']:
                    raise ValueError('Original native failure changed')
            row = next(x for x in active_rows(attempt_counts()) if x['task_id'] == ident)
            admitted = n.prepare_identity(row)
            state(ident, 'EXACT_ORIGINAL_IMAGE_AND_INITIAL_STATE_ON17')
            n.freeze(S / 'image-materializations' / (ident + '.json'), await asyncio.to_thread(n.ensure_resident, admitted))
            n.freeze(S / 'initial-outcomes' / (ident + '.json'), await asyncio.to_thread(n.initial, admitted))
            subnet = str(ipaddress.ip_network((int(ipaddress.ip_address('10.243.0.0')) + index * 16, 28)))
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
                n.freeze(dispatch_dir / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                    trial_name=cfg.trial_name, config_sha256=n.sha(dispatch_dir / 'trial-config.json'),
                    model_calls=0, environment_recheck_only=True, precheck_only_subnet=subnet))
                result = await queue.submit(cfg)
                trial = S / 'trials' / cfg.trial_name
                out['native_' + kind + '_trial'] = str(trial)
                out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                n.freeze(S / 'ssd-trial-archives' / (trial.name + '.json'), await asyncio.to_thread(n.archive_trial, trial))
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native recheck lifecycle failed: ' + str(result.exception_info))
                if kind == 'nop':
                    out['nop_reward'] = n.verify_nop(result, trial, admitted)
            if attempt_counts().get(ident, 0):
                out.update(status='ALREADY_STARTED_TASK_PRESERVED', reason='Teacher began before readiness publication')
                continue
            out.update(status='ENV_READY', admitted_task=admitted, engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA, placement=admitted['deployment_assignment'],
                placement_sha256=admitted['deployment_assignment_sha256'], source_sha256=frozen['source_sha256'])
        except Exception as error:
            out.update(error_type=type(error).__name__, reason=str(error)[-1800:])
        finally:
            path = S / 'environment-outcomes' / (ident + '.json')
            n.freeze(path, out)
            if out['status'] == 'ENV_READY':
                ready = dict(out, raw_outcome=str(path), raw_outcome_sha256=n.sha(path))
                digest = hashlib.sha256(json.dumps(ready, sort_keys=True).encode()).hexdigest()
                n.freeze(n.D / 'ready-revisions' / ident / (digest + '.json'), ready)
            if admitted is not None:
                try:
                    n.freeze(S / 'image-release' / (ident + '.json'), await asyncio.to_thread(n.release_cold_cache, admitted))
                except Exception as error:
                    n.freeze(S / 'image-release-errors' / (ident + '.json'), dict(error_type=type(error).__name__, reason=str(error)[-800:]))
            terminal[ident] = out['status']
            state(ident, 'TASK_NATIVE_RECHECK_TERMINAL')
            print(json.dumps(dict(task_id=ident, status=out['status'], reason=out.get('reason'))), flush=True)
    state(None, 'FINITE_NATIVE_RECHECK_TERMINAL')
    n.freeze(S / 'TERMINAL.json', json.loads((S / 'state.json').read_text()))


if __name__ == '__main__':
    os.environ['PATH'] = str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(main())
