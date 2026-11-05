"""One inactive native CLI/cache and official NOP prototype; no Teacher or Ready publication.

No Teacher admission, no model credentials, no Task replacement. New immutable
Ready evidence can supersede a setup block; every original failure is retained.
"""
import asyncio
from collections import Counter
import datetime
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from harbor.models.job.config import RetryConfig
from harbor.trial.queue import TrialQueue
from collection_attempts_r8 import attempt_counts
from collection_selection_r7 import active_rows
import collection_readiness_r19 as n

S = n.R / 'stream/public-cpython-native-prototype17-r267'
OLD = Path(n.DEPLOYMENT['controller_root'])


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def uncompleted(ident):
    for path in (n.R / 'stream/collection-r4/staging-dispatches').glob('*/setup.json'):
        value = json.loads(path.read_text())
        if value['task_id'] == ident and not (n.R / 'stream/collection-r4/trials' / value['trial_name'] / 'result.json').exists():
            return True
    return False


def plan():
    counts = attempt_counts()
    selected = {x['task_id']:x for x in active_rows(counts)}
    admissions = {json.loads(line)['trial_name'] for line in (n.R / 'stream/collection-r4/teacher-lifecycle.jsonl').open()
                  if json.loads(line)['event'] == 'TEACHER_ADMITTED'}
    items = {}
    for path in sorted((OLD / 'setup-failures').glob('*.json')):
        value = json.loads(path.read_text())
        ident = value['task_id']
        result_path = Path(value['native_result'])
        result = json.loads(result_path.read_text())
        if result.get('agent_execution') or result_path.parent.name in admissions or (result_path.parent / 'agent/openharness-rollout/events.jsonl').exists():
            raise ValueError('Setup-only recovery contains Teacher/Recorder evidence')
        if not result.get('finished_at') or value.get('model_calls') != 0:
            raise ValueError('Original pre-Agent setup is not terminal')
        if counts.get(ident, 0) >= 2 or n.blocking_review(ident) or uncompleted(ident):
            continue
        items[ident] = dict(task_id=ident, pool=selected[ident]['pool'], source_failure=str(path),
            source_failure_sha256=n.sha(path), original_result=str(result_path), original_result_sha256=n.sha(result_path),
            existing_attempt_budget_used=counts.get(ident, 0), teacher_trials_unchanged=True)
    tasks = [item for item in items.values() if item['task_id']=='task_007402_0a45b61a']
    if len(tasks) != 1:
        raise ValueError('Unexpected finite setup-recheck scope')
    return dict(checked_at=now(), tasks=tasks, native_concurrency=1, model_calls=0, teacher_dispatches=0,
        source_sha256=n.sha(Path(__file__)), deployment_config_sha256=n.CONFIG_SHA,
        prototype_only=True,ready_publication=False,cache_compose_sha256=n.sha(n.R/'configs/public-cpython-bootstrap-r266.compose.json'),cache_script_sha256=n.sha(n.R/'configs/public-cpython-bootstrap-r266.py'),
        runtime_node='17', engine_id=n.NODE['engine_id'], original_failures_preserved=True,
        environment_passes_per_task_in_this_plan=1, original_task_resources_and_verifier_timeouts=True)


async def main():
    S.mkdir(parents=True, exist_ok=True)
    lock = (S / 'worker.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (S / 'PLAN.json').exists():
        raise FileExistsError('Inspect existing finite native pass; no implicit replay')
    frozen = plan()
    n.freeze(S / 'PLAN.json', frozen)
    queue = TrialQueue(n_concurrent=1, retry_config=RetryConfig(max_retries=0))
    terminal = {}

    def state(ident, stage):
        value = dict(pid=os.getpid(), checked_at=now(), planned=len(frozen['tasks']), terminal=len(terminal),
            current_task_id=ident, stage=stage, native_concurrency=1, model_calls=0, teacher_dispatches=0,
            counts=dict(Counter(terminal.values())))
        temporary = S / 'state.pending'
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(S / 'state.json')

    for item in frozen['tasks']:
        ident = item['task_id']
        admitted = None
        out = dict(**item, status='ENV_FAILED', model_calls=0, teacher_dispatches=0,
            original_task_or_tests_modified=False, teacher_success_not_implied=True)
        try:
            for key in ['source_failure', 'original_result']:
                if n.sha(Path(item[key])) != item[key + '_sha256']:
                    raise ValueError('Original pre-Agent failure identity changed')
            if uncompleted(ident):
                out.update(status='EXISTING_NATIVE_TRIAL_PRESERVED', reason='No overlapping preparation for the same Task')
                continue
            counts = attempt_counts()
            if counts.get(ident, 0) != item['existing_attempt_budget_used']:
                out.update(status='TASK_ADMISSION_CHANGED_PRESERVED', reason='Existing admission progressed; no recheck')
                continue
            row = next(x for x in active_rows(counts) if x['task_id'] == ident)
            admitted = n.prepare_identity(row)
            state(ident, 'EXACT_ORIGINAL_IMAGE_AND_INITIAL_STATE_ON17')
            n.freeze(S / 'image-materializations' / (ident + '.json'), await asyncio.to_thread(n.ensure_resident, admitted))
            n.freeze(S / 'initial-outcomes' / (ident + '.json'), await asyncio.to_thread(n.initial, admitted))
            for kind in ['install', 'nop']:
                state(ident, 'NATIVE_' + kind.upper() + '_ON17')
                cfg = n.native_config(admitted, kind)
                cfg.trials_dir = S / 'trials'
                cfg.environment.extra_docker_compose=[*(cfg.environment.extra_docker_compose or []),n.R/'configs/public-cpython-bootstrap-r266.compose.json']
                if kind == 'install':
                    cfg.agent.env = {}
                directory = S / 'dispatches' / str(uuid4())
                directory.mkdir(parents=True)
                (directory / 'trial-config.json').write_text(cfg.model_dump_json(indent=2))
                n.freeze(directory / 'dispatch.json', dict(task_id=ident, pool=row['pool'], kind=kind,
                    trial_name=cfg.trial_name, config_sha256=n.sha(directory / 'trial-config.json'),
                    model_calls=0, environment_recheck_only=True))
                result = await queue.submit(cfg)
                trial = S / 'trials' / cfg.trial_name
                out['native_' + kind + '_trial'] = str(trial)
                out[kind + '_result_sha256'] = n.sha(trial / 'result.json')
                n.freeze(S / 'ssd-trial-archives' / (trial.name + '.json'), await asyncio.to_thread(n.archive_trial, trial))
                if result.exception_info or result.infrastructure_errors:
                    raise ValueError('Native recheck lifecycle failed: ' + str(result.exception_info))
                if kind == 'nop':
                    out['nop_reward'] = n.verify_nop(result, trial, admitted)
            if attempt_counts().get(ident, 0) != item['existing_attempt_budget_used']:
                out.update(status='TASK_ADMISSION_CHANGED_PRESERVED', reason='No Ready publication after changed Teacher admission')
                continue
            out.update(status='ENV_READY', admitted_task=admitted, engine_id=n.NODE['engine_id'],
                deployment_config_sha256=n.CONFIG_SHA, placement=admitted['deployment_assignment'],
                placement_sha256=admitted['deployment_assignment_sha256'], source_sha256=frozen['source_sha256'])
        except Exception as error:
            out.update(error_type=type(error).__name__, reason=str(error)[-1800:])
        finally:
            path = S / 'environment-outcomes' / (ident + '.json')
            n.freeze(path, out)
            # Inactive prototype evidence only: never publish Ready to R19.
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
    os.environ['PATH'] = n.DEPLOYMENT['native_client_bin'] + ':' + str(n.R / 'client-bin-v2') + ':' + os.environ['PATH']
    os.environ['SSH_AUTH_SOCK'] = '/home/chenkeyi/.local/share/harbor-rsi/near-r3-20261015/auth.sock'
    for name in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'GH_TOKEN']:
        os.environ.pop(name, None)
    asyncio.run(main())
